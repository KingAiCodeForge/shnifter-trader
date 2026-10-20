"""Causal research screening across expanding chronological folds, not a live-trading gate.

Selects a strategy using ONLY earlier validation bars, then tests the selected
strategy on subsequent bars. Results are research evidence, not live approval.
No network, broker, LLM, state mutation or secret access is used.
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_FLOOR
from typing import Iterable

from shnifter_replay import (Bar, ReplayConfig, normalise_bars, run_replay,
                             _fee, _fill_price, _money)

CANDIDATES = ((5, 20), (10, 30), (20, 50), (20, 100))
VERSION = "shnifter.oos-fold-evaluator.v2"


@dataclass(frozen=True)
class GatePolicy:
    folds: int = 3
    validation_bars: int = 80
    test_bars: int = 80
    min_prior_bars: int = 150
    fee_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("5")
    stress_multiplier: Decimal = Decimal("2")
    max_position_pct: Decimal = Decimal("0.20")
    initial_cash: Decimal = Decimal("10000")
    min_total_completed_trades: int = 4
    min_mean_excess_return_pct: Decimal = Decimal("1")
    max_test_drawdown_pct: Decimal = Decimal("20")
    candidates: tuple[tuple[int, int], ...] = CANDIDATES

    def __post_init__(self):
        # API callers may supply ordinary JSON numbers or decimal strings.
        # Normalise once; booleans are not monetary/risk values.
        for name in ("fee_bps", "slippage_bps", "stress_multiplier", "max_position_pct",
                     "initial_cash", "min_mean_excess_return_pct", "max_test_drawdown_pct"):
            raw = getattr(self, name)
            if type(raw) not in (Decimal, int, float, str):
                raise ValueError(f"{name} must be a finite decimal")
            try:
                value = Decimal(str(raw))
            except (ValueError, ArithmeticError) as exc:
                raise ValueError(f"{name} must be a finite decimal") from exc
            if not value.is_finite():
                raise ValueError(f"{name} must be finite")
            object.__setattr__(self, name, value)

    def validate(self):
        for name in ("folds", "validation_bars", "test_bars", "min_prior_bars",
                     "min_total_completed_trades"):
            value = getattr(self, name)
            if type(value) is not int or value < (0 if name == "min_total_completed_trades" else 1):
                raise ValueError(f"{name} must be a positive integer")
        if not 1 <= self.folds <= 8 or not 50 <= self.validation_bars <= 1000 or not 50 <= self.test_bars <= 1000:
            raise ValueError("folds or window size out of bounds")
        if type(self.candidates) is not tuple or not 1 <= len(self.candidates) <= 12:
            raise ValueError("provide 1..12 fixed candidate SMA pairs")
        for pair in self.candidates:
            if (not isinstance(pair, tuple) or len(pair) != 2 or
                not all(type(x) is int for x in pair) or not 2 <= pair[0] < pair[1] <= 250):
                raise ValueError("candidate SMA windows must satisfy 2 <= fast < slow <= 250")
        if len(set(self.candidates)) != len(self.candidates):
            raise ValueError("duplicate candidate SMA pairs")
        if self.min_prior_bars > 10000 or self.min_total_completed_trades > 100000:
            raise ValueError("prior history or trade-count threshold out of bounds")
        for name in ("fee_bps", "slippage_bps", "stress_multiplier", "max_position_pct",
                     "initial_cash", "min_mean_excess_return_pct", "max_test_drawdown_pct"):
            x = Decimal(str(getattr(self, name)))
            if not x.is_finite():
                raise ValueError(f"{name} must be finite")
        if not (0 <= self.fee_bps <= 1000 and 0 <= self.slippage_bps <= 1000):
            raise ValueError("fee/slippage bps must be between 0 and 1000")
        if not (1 <= self.stress_multiplier <= 5 and
                self.fee_bps * self.stress_multiplier < 10000 and
                self.slippage_bps * self.stress_multiplier < 10000):
            raise ValueError("invalid cost-stress multiplier")
        if not (0 < self.max_position_pct <= Decimal("0.5") and self.initial_cash >= 100):
            raise ValueError("position cap or initial equity invalid")
        if not (0 <= self.min_mean_excess_return_pct <= 100 and
                0 < self.max_test_drawdown_pct <= 90):
            raise ValueError("invalid performance acceptance limit")


def _snapshot(bars: list[Bar]) -> str:
    records = [{k: str(v) for k, v in asdict(bar).items()} for bar in bars]
    return json.dumps(records, sort_keys=True, separators=(",", ":"))


def _replay(bars: list[Bar], start: int, end: int, fast: int, slow: int,
            policy: GatePolicy, ticker: str, stress: bool = False) -> dict:
    # Warm up on *only* known earlier prices. Replayer can't trade until all
    # slow bars have closed, so no simulated fill occurs in the warmup.
    if start - slow < 0 or end - start < 2:
        raise ValueError("insufficient pre-window warmup bars")
    mult = policy.stress_multiplier if stress else Decimal(1)
    cfg = ReplayConfig(
        initial_cash=policy.initial_cash, fast_window=fast, slow_window=slow,
        max_position_pct=policy.max_position_pct,
        fee_bps=policy.fee_bps * mult,
        slippage_bps=policy.slippage_bps * mult,
        max_drawdown_pct=min(Decimal("0.20"), policy.max_test_drawdown_pct / 100),
        stop_loss_pct=Decimal("0.05"), take_profit_pct=Decimal("0.10"),
    )
    return run_replay(bars[start-slow:end], cfg, ticker=ticker)


def _profit_factor(trades: list[dict]) -> float | None:
    wins = sum(float(t["pnl"]) for t in trades if t["pnl"] > 0)
    losses = -sum(float(t["pnl"]) for t in trades if t["pnl"] < 0)
    return round(wins / losses, 5) if losses > 0 else None


def _per_bar_risk_ratio(report: dict, warmup: int) -> float | None:
    curve = report["equity_curve"][warmup:]
    previous = report["initial_cash"]
    daily = []
    for bar in curve:
        value = float(bar["equity"])
        if previous <= 0 or value <= 0:
            return None
        daily.append(value / previous - 1)
        previous = value
    if len(daily) < 50:
        return None
    std = statistics.stdev(daily)
    return round(statistics.mean(daily) / std, 5) if std > 0 else None


def _summary(report: dict, warmup: int) -> dict:
    return {"return_pct": report["total_return_pct"],
            "max_drawdown_pct": report["max_drawdown_pct"],
            "closed_trades": report["completed_trades"],
            "fills": len(report["fills"]),
            "profit_factor": _profit_factor(report["trades"]),
            "mean_over_std_per_bar_not_annualised": _per_bar_risk_ratio(report, warmup),
            "open_position_at_end": report["open_position"] is not None,
            "run_id": report["run_id"]}


def _buy_hold(bars: list[Bar], start: int, end: int, policy: GatePolicy,
              stress: bool = False) -> dict:
    """Use the strategy's cent-rounded execution costs and initial NAV peak.

    Buy once at the first test open; remaining shares are marked at the last
    close, not sold. No exit fees are invented for an unexecuted liquidation.
    """
    mult = policy.stress_multiplier if stress else Decimal(1)
    cfg = ReplayConfig(fee_bps=policy.fee_bps * mult,
                       slippage_bps=policy.slippage_bps * mult)
    initial = _money(policy.initial_cash)
    entry = _fill_price(bars[start].open, "BUY", cfg)
    if entry <= 0:
        raise ValueError("benchmark fill price rounds to zero")
    budget = _money(initial * policy.max_position_pct)
    shares = int((budget / (entry * (1 + cfg.fee_bps / 10000)))
                 .to_integral_value(rounding=ROUND_FLOOR))
    commission = _fee(entry * shares, cfg)
    while shares > 0 and entry * shares + commission > budget:
        shares -= 1
        commission = _fee(entry * shares, cfg)
    cash = initial - entry * shares - commission
    peak = initial  # Include entry fees, spread and any first-bar loss.
    worst = Decimal(0)
    for bar in bars[start:end]:
        equity = cash + shares * bar.close
        peak = max(peak, equity)
        worst = max(worst, (peak - equity) / peak)
    final = cash + shares * bars[end-1].close
    return {"return_pct": round(float((final / initial - 1) * 100), 5),
            "max_drawdown_pct": round(float(worst * 100), 5),
            "shares": shares, "entry_price": float(entry),
            "entry_fee": float(commission), "cash": float(cash),
            "final_equity": float(_money(final)),
            "benchmark": "same-cap buy-and-hold; cash remainder"}


def evaluate_oos(bars: Iterable[Bar], *, ticker: str, policy: GatePolicy | None = None) -> dict:
    policy = GatePolicy() if policy is None else policy
    if not isinstance(policy, GatePolicy):
        raise ValueError("policy must be GatePolicy")
    policy.validate()
    if not isinstance(ticker, str) or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^_=-]{0,31}", ticker):
        raise ValueError("ticker must be a single valid symbol")
    bars = list(bars)
    if not 1 <= len(bars) <= 10000:
        raise ValueError("daily OHLCV rows must be in 1..10000")
    bars = normalise_bars([asdict(bar) for bar in bars])
    n = len(bars)
    max_slow = max(slow for _, slow in policy.candidates)
    earliest_test = n - policy.folds * policy.test_bars
    if earliest_test - policy.validation_bars < max(policy.min_prior_bars, max_slow):
        raise ValueError("not enough chronological bars for requested folds and warmup")
    fingerprints = {"data_sha256": hashlib.sha256(_snapshot(bars).encode()).hexdigest(),
                    "policy_sha256": hashlib.sha256(json.dumps(
                        asdict(policy), sort_keys=True, default=str).encode()).hexdigest()}
    eval_id = hashlib.sha256(json.dumps(
        {"ticker": ticker, "version": VERSION, **fingerprints},
        sort_keys=True).encode()).hexdigest()[:32]
    fold_results = []
    for fold in range(policy.folds):
        test_start = earliest_test + fold * policy.test_bars
        test_end = test_start + policy.test_bars
        val_start = test_start - policy.validation_bars
        val_end = test_start
        standings = []
        for fast, slow in policy.candidates:
            report = _replay(bars, val_start, val_end, fast, slow, policy, ticker)
            val = _summary(report, slow)
            # Predeclared score uses VALIDATION ONLY. No test result or ML
            # probability can influence which candidate is selected.
            score = val["return_pct"] - .25 * val["max_drawdown_pct"] - .02 * val["fills"]
            standings.append({"fast": fast, "slow": slow,
                              "selection_score": round(score, 6), **val})
        standings.sort(key=lambda v: (-v["selection_score"], v["fast"], v["slow"]))
        selected = standings[0]
        fast, slow = selected["fast"], selected["slow"]
        test = _summary(_replay(bars, test_start, test_end, fast, slow, policy, ticker), slow)
        stress = _summary(_replay(bars, test_start, test_end, fast, slow, policy, ticker, True), slow)
        hold = _buy_hold(bars, test_start, test_end, policy)
        stress_hold = _buy_hold(bars, test_start, test_end, policy, True)
        fold_results.append({
            "fold": fold + 1,
            "prior_history_end_exclusive": bars[val_start].date,
            "validation": {"start": bars[val_start].date, "end": bars[val_end-1].date,
                           "standings": standings},
            "test": {"start": bars[test_start].date, "end": bars[test_end-1].date,
                     "strategy": test, "stressed_costs": stress,
                     "buy_and_hold": hold, "stressed_buy_and_hold": stress_hold,
                     "cash_return_pct": 0},
            "selected": {"fast": fast, "slow": slow},
        })
    returns = [row["test"]["strategy"]["return_pct"] for row in fold_results]
    excesses = [row["test"]["strategy"]["return_pct"] -
                row["test"]["buy_and_hold"]["return_pct"] for row in fold_results]
    stressed = [row["test"]["stressed_costs"]["return_pct"] for row in fold_results]
    total_trades = sum(row["test"]["strategy"]["closed_trades"] for row in fold_results)
    max_dd = max(row["test"]["strategy"]["max_drawdown_pct"] for row in fold_results)
    reasons = []
    if total_trades < policy.min_total_completed_trades:
        reasons.append("insufficient completed trades")
    if statistics.mean(excesses) < float(policy.min_mean_excess_return_pct):
        reasons.append("mean benchmark excess return below threshold")
    if statistics.mean(returns) <= 0:
        reasons.append("mean net return nonpositive")
    if statistics.mean(stressed) <= 0:
        reasons.append("cost-stressed mean return nonpositive")
    if max_dd > float(policy.max_test_drawdown_pct):
        reasons.append("test drawdown exceeds cap")
    eligible = not reasons
    report = {
        "ok": True, "engine": VERSION, "ticker": ticker, "evaluation_id": eval_id, **fingerprints,
        "bars": n, "first_date": bars[0].date, "last_date": bars[-1].date,
        "settings": json.loads(json.dumps(asdict(policy), default=str)),
        "folds": fold_results,
        "summary": {"mean_net_return_pct": round(statistics.mean(returns), 5),
                    "mean_excess_vs_sized_buy_hold_pct": round(statistics.mean(excesses), 5),
                    "mean_stressed_return_pct": round(statistics.mean(stressed), 5),
                    "max_test_drawdown_pct": max_dd,
                    "completed_trades": total_trades,
                    "paper_research_candidate": eligible,
                    "rejection_reasons": reasons,
                    "live_authorized": False},
        "limitations": [
            "Synthetic or user-provided OHLCV has no verified point-in-time provenance",
            "Validation selects only preceding data; earlier tests may be used as later validation",
            "Repeated inspection/tuning against this report invalidates it as a fresh holdout",
            "One stock and one strategy family cannot establish robust live alpha",
            "No split/dividend/FX/borrow/liquidity/margin/broker partial-fill handling",
            "Each fold restarts flat; fold returns are not one continuous portfolio NAV",
            "Per-bar mean/std is unannualised; no verified exchange calendar or risk-free series",
            "All performance figures are backtests, never real or guaranteed",
        ]}
    return report
