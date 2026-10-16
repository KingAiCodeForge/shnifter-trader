from core.shnifter_trade import Trade, Portfolio

# Model/LLM confidence is NOT a calibrated probability of profit.
# The legacy API keeps its signature but deliberately ignores confidence and
# Kelly parameters. All live allocation must use independent risk limits.
import math


def calculate_position_size(confidence, balance, risk_per_trade=0.01, kelly_fraction=1.0):
    """Return a strictly bounded cash risk budget, never LLM-weighted.

    Compatibility with the previous signature is preserved for GUI/tests,
    but confidence is not used for sizing. This is a *currency budget*, not
    an executable share quantity; use size_from_stop_distance for units.
    """
    if not math.isfinite(balance) or balance <= 0:
        raise ValueError("balance must be positive and finite")
    if not math.isfinite(risk_per_trade) or not 0 < risk_per_trade <= 0.05:
        raise ValueError("risk_per_trade must be in (0, 0.05]")
    return float(balance) * float(risk_per_trade)


def size_from_stop_distance(*, capital, entry_price, stop_price,
                            max_risk_fraction=0.01, max_position_fraction=0.20):
    """Whole-share long size bounded by loss-to-stop and gross position value.

    Stop orders can gap or fail to fill, so actual losses can exceed this
    nominal estimate. Independent drawdown and execution gates are required.
    This function does not place, propose, or approve an order.
    """
    inputs = (capital, entry_price, stop_price, max_risk_fraction, max_position_fraction)
    if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in inputs):
        raise ValueError("risk inputs must be finite numbers")
    if capital <= 0 or entry_price <= 0 or not (0 < stop_price < entry_price):
        raise ValueError("require positive capital, entry and lower long stop")
    if not (0 < max_risk_fraction <= 0.05 and 0 < max_position_fraction <= 1):
        raise ValueError("risk and exposure fractions out of bounds")
    qty_loss = math.floor((capital * max_risk_fraction) / (entry_price - stop_price))
    qty_value = math.floor((capital * max_position_fraction) / entry_price)
    return max(0, min(qty_loss, qty_value))

# Example: Portfolio heat and drawdown checks

def get_portfolio_heat(portfolio, price_lookup):
    """
    Returns total risk exposure as a fraction of balance.
    """
    total_risk = 0
    for trade in portfolio.get_open_trades():
        # Risk per trade = abs(entry - stop) * size
        risk = abs(trade.entry - trade.stop) * trade.size
        total_risk += risk
    return total_risk / portfolio.balance if portfolio.balance > 0 else 0

def check_drawdown(portfolio, max_drawdown=0.2):
    """
    Returns True if drawdown exceeds max_drawdown (e.g., 20%).
    """
    return portfolio.max_drawdown >= max_drawdown
