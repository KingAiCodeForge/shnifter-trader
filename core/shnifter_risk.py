"""Deterministic risk estimates for simulated Shnifter portfolios.

Unknown exposure must never be represented as zero. This module is a research
helper; it is not a complete production broker pre-trade risk controller.
"""
from __future__ import annotations

import math


def _finite_positive(value) -> bool:
    """Reject bools and non-numeric/unbounded values for risk accounting."""
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def calculate_position_size(confidence, balance, risk_per_trade=0.01, kelly_fraction=1.0):
    """Cash risk budget, unrelated to uncalibrated LLM/model confidence.

    Signature preserved for callers. This amount is not order share quantity.
    """
    if not _finite_positive(balance):
        raise ValueError("balance must be positive and finite")
    if not _finite_positive(risk_per_trade) or risk_per_trade > 0.05:
        raise ValueError("risk_per_trade must be in (0, 0.05]")
    return float(balance) * float(risk_per_trade)


def size_from_stop_distance(*, capital, entry_price, stop_price,
                            max_risk_fraction=0.01, max_position_fraction=0.20):
    """Whole shares bounded by nominal stop risk and gross exposure.

    Not guaranteed: stop fills can gap, slip or be rejected. Long-only.
    """
    inputs = (capital, entry_price, stop_price, max_risk_fraction, max_position_fraction)
    if not all(type(x) in (int, float) and math.isfinite(x) for x in inputs):
        raise ValueError("risk inputs must be finite numbers")
    if capital <= 0 or entry_price <= 0 or not (0 < stop_price < entry_price):
        raise ValueError("require positive capital, entry and lower long stop")
    if not (0 < max_risk_fraction <= 0.05 and 0 < max_position_fraction <= 1):
        raise ValueError("risk and exposure fractions out of bounds")
    qty_loss = math.floor((capital * max_risk_fraction) / (entry_price - stop_price))
    qty_value = math.floor((capital * max_position_fraction) / entry_price)
    return max(0, min(qty_loss, qty_value))


def get_portfolio_heat(portfolio, price_lookup):
    """Estimate nominal stop-distance exposure divided by available balance.

    Returns +infinity if balance, direction, stop or quantity is missing,
    invalid or inconsistent. Unknown risk must never become 0% merely because
    a denominator is zero or a protective stop was not supplied.

    price_lookup is retained for existing callers; entry-to-stop exposure
    is deliberately independent of fluctuating marks. This is not gap VaR.
    """
    balance = getattr(portfolio, "balance", None)
    if not _finite_positive(balance):
        return math.inf
    total_risk = 0.0
    for trade in portfolio.get_open_trades():
        entry = getattr(trade, "entry", None)
        stop = getattr(trade, "stop", None)
        size = getattr(trade, "size", None)
        direction = getattr(trade, "direction", None)
        if not (_finite_positive(entry) and _finite_positive(stop)
                and _finite_positive(size)):
            return math.inf
        if direction == 'long':
            if not stop < entry:
                return math.inf
            distance = entry - stop
        elif direction == 'short':
            if not stop > entry:
                return math.inf
            distance = stop - entry
        else:
            return math.inf
        total_risk += distance * size
        if not math.isfinite(total_risk):
            return math.inf
    return total_risk / balance


def check_drawdown(portfolio, max_drawdown=0.2):
    """Return True when drawdown violates the threshold OR data is invalid."""
    actual = getattr(portfolio, "max_drawdown", None)
    if not (type(actual) in (int, float) and math.isfinite(actual)
            and 0 <= actual <= 1):
        return True
    if not (type(max_drawdown) in (int, float) and math.isfinite(max_drawdown)
            and 0 < max_drawdown <= 1):
        return True
    return actual >= max_drawdown
