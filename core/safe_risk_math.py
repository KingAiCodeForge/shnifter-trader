"""Pure, fail-closed risk calculations for research and paper execution.

No broker connectivity; no LLM confidence; no account-state mutation. These
functions do not authorise live trading. Live account positions and quotes must
be reconciled and freshness-checked by a separate, tested execution gateway.
"""
from __future__ import annotations

import re
from decimal import Decimal, ROUND_FLOOR, InvalidOperation
from collections.abc import Mapping


def amount(value, name: str, *, allow_zero: bool = False) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError(f"{name} must be a finite decimal")
    try:
        val = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite decimal") from exc
    if not val.is_finite() or val < 0 or (not allow_zero and val == 0):
        raise ValueError(f"{name} must be finite and {'nonnegative' if allow_zero else 'positive'}")
    return val


def whole_share_size(*, equity, risk_fraction, entry, stop, max_asset_fraction,
                     max_position_value) -> Decimal:
    """Return a capped whole-share long quantity, or reject invalid inputs.

    Loss-to-stop is *not* maximum possible loss. Gaps can exceed stops.
    Uncalibrated confidence scores never change size.
    """
    cash = amount(equity, "equity")
    risk = amount(risk_fraction, "risk_fraction")
    price = amount(entry, "entry")
    protective = amount(stop, "stop")
    asset_cap = amount(max_asset_fraction, "max_asset_fraction")
    value_cap = amount(max_position_value, "max_position_value")
    if risk > Decimal("0.02") or asset_cap > 1 or protective >= price:
        raise ValueError("risk cap or long-stop geometry invalid")
    quantity = min(
        (cash * risk / (price - protective)).to_integral_value(rounding=ROUND_FLOOR),
        (cash * asset_cap / price).to_integral_value(rounding=ROUND_FLOOR),
        (value_cap / price).to_integral_value(rounding=ROUND_FLOOR),
    )
    return quantity


def check_proposed_order(*, equity, positions: Mapping, symbol: str, side: str,
                         quantity, market_price, order_price=None,
                         max_position_value, max_asset_fraction,
                         max_portfolio_fraction, daily_pnl,
                         max_daily_loss, entry_halted: bool = False) -> tuple[bool, str]:
    """Conservative long-only pretrade decision from an explicit position snapshot.

    A SELL is allowed during an entry halt only if it is demonstrably reducing
    an existing long position. Unknown holdings are never presumed to be zero.
    For BUY, evaluate *projected* exposures including the proposed order.
    """
    try:
        if not isinstance(positions, Mapping):
            return False, "no authoritative position snapshot"
        if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^_=-]{0,31}", symbol):
            return False, "invalid instrument"
        if side not in ("BUY", "SELL"):
            return False, "unsupported order direction"
        cash = amount(equity, "equity")
        px = amount(market_price, "market_price")
        units = amount(quantity, "quantity")
        if units != units.to_integral_value():
            return False, "whole-share quantity required"
        value = units * px
        if order_price is not None:
            limit = amount(order_price, "order_price")
            if abs(limit - px) / px >= Decimal("0.10"):
                return False, "order price deviates >=10% from market"
        pos_limit = amount(max_position_value, "max_position_value")
        asset_limit = amount(max_asset_fraction, "max_asset_fraction")
        port_limit = amount(max_portfolio_fraction, "max_portfolio_fraction")
        loss_limit = amount(max_daily_loss, "max_daily_loss")
        if asset_limit > 1 or port_limit > 1:
            return False, "exposure fractions must be <=1"
        realised = Decimal(str(daily_pnl))
        if not realised.is_finite():
            return False, "daily P&L unavailable"
        aggregate = Decimal(0)
        asset_value = Decimal(0)
        asset_units = Decimal(0)
        for ticker, state in positions.items():
            if not isinstance(ticker, str) or not isinstance(state, Mapping):
                return False, "invalid position snapshot"
            exposure = amount(state.get("value"), f"{ticker} value", allow_zero=True)
            shares = amount(state.get("quantity"), f"{ticker} quantity", allow_zero=True)
            if shares != shares.to_integral_value():
                return False, "fractional holdings not supported by this controller"
            if (shares == 0) != (exposure == 0):
                return False, "inconsistent quantity and value"
            aggregate += exposure
            if ticker == symbol:
                asset_value, asset_units = exposure, shares
        if side == "SELL":
            if asset_units < units:
                return False, "sell not provably closing existing long shares"
            return True, "risk-reducing long sale (paper-only validation)"
        if entry_halted:
            return False, "risk halt active"
        if realised <= -loss_limit:
            return False, "daily loss limit reached"
        if value > pos_limit:
            return False, "single order value cap"
        if aggregate + value > cash * port_limit:
            return False, "projected portfolio exposure cap"
        if asset_value + value > cash * asset_limit:
            return False, "projected asset exposure cap"
        return True, "bounded long entry (paper-only validation)"
    except (TypeError, ValueError, ArithmeticError) as exc:
        return False, f"invalid risk input: {exc}"
