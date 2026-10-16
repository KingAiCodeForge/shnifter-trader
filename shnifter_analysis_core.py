"""Headless, read-only signal analysis for Shnifter Trader.

Consumes completed historical closes. Does NOT place orders, call an LLM,
access a broker, or claim calibrated trade probabilities.
"""
from __future__ import annotations

import math
import re
from typing import Any


def _normalise_close(frame):
    """Reject ambiguous and broken data instead of fabricating price history."""
    import numpy as np
    import pandas as pd

    if frame is None or frame.empty:
        raise ValueError("price history is empty")
    columns = frame.columns
    matches = [c for c in columns if (
        any(str(p).lower() == "close" for p in c) if isinstance(c, tuple)
        else str(c).lower() == "close"
    )]
    if len(matches) != 1:
        raise ValueError("expected exactly one close-price column")
    close = frame.loc[:, matches[0]]
    if isinstance(close, pd.DataFrame):
        raise ValueError("ambiguous multi-symbol close prices")
    try:
        close = pd.to_numeric(close, errors="raise").astype(float)
    except (TypeError, ValueError) as exc:
        raise ValueError("non-numeric close prices") from exc
    if close.isna().any() or not np.isfinite(close.to_numpy()).all() or (close <= 0).any():
        raise ValueError("close prices must be finite and positive")
    if close.index.has_duplicates or not close.index.is_monotonic_increasing:
        raise ValueError("price index must be chronological and unique")
    return close.copy()


def evaluate_signals(frame, *, ticker: str, fast: int = 20, slow: int = 50,
                     min_labeled: int = 80, use_ml: bool = True) -> dict[str, Any]:
    """Emit a research signal and an honest one-step-ahead ML evaluation.

    For a labelled feature on day t, its outcome is close[t+1] > close[t].
    The latest row t_final is NEVER given a training target. A one-row
    chronological gap separates the model's training and evaluation sets.
    HOLD means insufficient corroborating evidence, not a brokerage order.
    """
    import numpy as np
    import pandas as pd

    if not re.fullmatch(r"[A-Za-z0-9^][A-Za-z0-9.^_=-]{0,31}", ticker):
        raise ValueError("invalid single-symbol ticker")
    if not (isinstance(fast, int) and isinstance(slow, int) and 1 <= fast < slow <= 250):
        raise ValueError("required: 1 <= fast < slow <= 250")
    if not isinstance(min_labeled, int) or min_labeled < 40:
        raise ValueError("min_labeled must be >= 40")
    close = _normalise_close(frame)
    if len(close) < slow:
        raise ValueError("not enough complete price bars for moving averages")

    fast_sma = float(close.iloc[-fast:].mean())
    slow_sma = float(close.iloc[-slow:].mean())
    trend = "BUY" if fast_sma > slow_sma else "SELL" if fast_sma < slow_sma else "HOLD"
    result: dict[str, Any] = {
        "ticker": ticker.upper(), "observations": len(close),
        "bar_asof": str(close.index[-1]),
        "trend": {"action": trend, "fast_window": fast, "slow_window": slow,
                  "fast_sma": fast_sma, "slow_sma": slow_sma},
        "ml": {"action": "HOLD", "status": "disabled" if not use_ml else "insufficient_data",
               "probability_up_uncalibrated": None, "validation_accuracy": None,
               "majority_baseline_accuracy": None, "validation_brier": None,
               "train_samples": 0, "test_samples": 0},
        "consensus": "HOLD",
        "execution_permission": "research_only",
    }
    if not use_ml:
        return result

    returns = close.pct_change()
    features = pd.DataFrame(index=close.index)
    features["return_1"] = returns
    features["momentum_5"] = close.pct_change(5)
    features["momentum_20"] = close.pct_change(20)
    features["volatility_20"] = returns.rolling(20, min_periods=20).std()
    # A valid label for observation t requires close at t+1.
    future = close.shift(-1)
    label = (future > close).astype(int)
    usable = features.notna().all(axis=1)
    labeled = usable & future.notna()
    X_labeled = features.loc[labeled]
    y_labeled = label.loc[labeled]
    if len(X_labeled) < min_labeled or not usable.iloc[-1]:
        return result

    split = int(len(X_labeled) * 0.8)
    # Omit one observation at the chronological boundary (a 1-day horizon).
    X_train, y_train = X_labeled.iloc[:split-1], y_labeled.iloc[:split-1]
    X_test, y_test = X_labeled.iloc[split:], y_labeled.iloc[split:]
    if len(X_train) < 30 or len(X_test) < 10:
        return result

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, brier_score_loss

    majority = int(y_train.mean() >= .5)
    baseline = float((y_test == majority).mean())
    ml = result["ml"]
    ml.update({"train_samples": len(X_train), "test_samples": len(X_test),
               "majority_baseline_accuracy": baseline,
               "train_last_bar": str(X_train.index[-1]),
               "test_first_bar": str(X_test.index[0]),
               "last_training_target_bar": str(close.index[close.index.get_loc(X_train.index[-1]) + 1])})
    if len(set(y_train)) < 2:
        ml.update({"status": "single_class", "action": "HOLD"})
        return result
    model = RandomForestClassifier(n_estimators=100, min_samples_leaf=5,
                                   random_state=42, n_jobs=1)
    model.fit(X_train, y_train)
    proba_test = model.predict_proba(X_test)[:, list(model.classes_).index(1)]
    ml.update({"validation_accuracy": float(accuracy_score(y_test, proba_test >= .5)),
               "validation_brier": float(brier_score_loss(y_test, proba_test))})
    # Fit a new model on all known historical labels ONLY; do not use the last
    # observation's unknown future outcome as a training example.
    prediction_model = RandomForestClassifier(n_estimators=100, min_samples_leaf=5,
                                              random_state=42, n_jobs=1)
    prediction_model.fit(X_labeled, y_labeled)
    probability = float(prediction_model.predict_proba(features.iloc[[-1]])[0,
                                  list(prediction_model.classes_).index(1)])
    if not math.isfinite(probability):
        raise ValueError("non-finite ML score")
    prediction = "BUY" if probability >= 0.55 else "SELL" if probability <= 0.45 else "HOLD"
    ml.update({"action": prediction, "status": "evaluated",
               "probability_up_uncalibrated": probability,
               "last_labeled_bar": str(X_labeled.index[-1])})
    if trend == prediction and prediction in ("BUY", "SELL"):
        result["consensus"] = prediction
    return result
