"""Shared, strictly read-only Shnifter research actions for CLI, API and MCP.

No broker, portfolio writer, order execution, credentials or LLM is imported.
Untrusted AI-generated arguments pass through the same validation here.
"""
from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any, Mapping

_ACTIONS = (
    {"name": "actions.list", "description": "Discover available Shnifter tools",
     "side_effects": "none", "capability": "read_only"},
    {"name": "analysis.signals", "description": "Calculate SMA and chronological RandomForest research signals from complete daily bars",
     "side_effects": "none", "capability": "read_only"},
    {"name": "backtest.replay", "description": "Deterministic long-only historical SMA strategy replay with fees and slippage",
     "side_effects": "none", "capability": "read_only"},
)
_ACTION_MAP = {item["name"]: item for item in _ACTIONS}
_MAX_ROWS = 10000


def list_actions() -> list[dict[str, str]]:
    return [dict(spec) for spec in _ACTIONS]


def _make_bars(rows: Any):
    from shnifter_replay import normalise_bars
    if not isinstance(rows, list) or not 2 <= len(rows) <= _MAX_ROWS:
        raise ValueError(f"rows must be a list of 2..{_MAX_ROWS} chronological daily bars")
    return normalise_bars(rows)


def _strict_params(name: str, args: Any, accepted: set[str], required: set[str]):
    if not isinstance(args, dict):
        raise ValueError("action parameters must be a JSON object")
    unknown = set(args) - accepted
    missing = required - set(args)
    if unknown or missing:
        raise ValueError(f"invalid {name} parameters: unknown={sorted(unknown)}, missing={sorted(missing)}")


def invoke_action(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Invoke a whitelisted research-only operation. Fail closed by default."""
    if name not in _ACTION_MAP:
        raise ValueError("unsupported read-only action; consult actions.list")
    params = {} if params is None else params
    if name == "actions.list":
        _strict_params(name, params, set(), set())
        return {"ok": True, "actions": list_actions()}
    if name == "analysis.signals":
        keys = {"ticker", "rows", "fast", "slow", "min_labeled", "use_ml"}
        _strict_params(name, params, keys, {"ticker", "rows"})
        from shnifter_analysis_core import evaluate_signals
        import pandas as pd
        bars = _make_bars(params["rows"])
        data = pd.DataFrame([{k: float(v) for k, v in asdict(bar).items() if k != "date"}
                             for bar in bars], index=pd.to_datetime([b.date for b in bars]))
        return {"ok": True, "action": name, "result": evaluate_signals(
            data, ticker=params["ticker"], fast=params.get("fast", 20),
            slow=params.get("slow", 50), min_labeled=params.get("min_labeled", 80),
            use_ml=params.get("use_ml", True))}
    if name == "backtest.replay":
        keys = {"ticker", "rows", "fast", "slow", "initial_cash", "max_position_pct",
                "stop_loss_pct", "take_profit_pct", "max_drawdown_pct", "fee_bps", "slippage_bps"}
        _strict_params(name, params, keys, {"ticker", "rows"})
        from shnifter_replay import ReplayConfig, run_replay
        import re
        ticker = params["ticker"]
        if not isinstance(ticker, str) or not re.fullmatch(r"[A-Za-z0-9^][A-Za-z0-9.^_=-]{0,31}", ticker):
            raise ValueError("ticker must be a single symbol")
        cfg = ReplayConfig(
            fast_window=params.get("fast", 20), slow_window=params.get("slow", 50),
            initial_cash=Decimal(str(params.get("initial_cash", '10000'))),
            max_position_pct=Decimal(str(params.get("max_position_pct", '.20'))),
            stop_loss_pct=Decimal(str(params.get("stop_loss_pct", '.05'))),
            take_profit_pct=Decimal(str(params.get("take_profit_pct", '.10'))),
            max_drawdown_pct=Decimal(str(params.get("max_drawdown_pct", '.20'))),
            fee_bps=Decimal(str(params.get("fee_bps", '10'))),
            slippage_bps=Decimal(str(params.get("slippage_bps", '5'))),
        )
        return {"ok": True, "action": name, "result": run_replay(
            _make_bars(params["rows"]), cfg, ticker=ticker)}
    raise AssertionError("registry and dispatcher out of sync")
