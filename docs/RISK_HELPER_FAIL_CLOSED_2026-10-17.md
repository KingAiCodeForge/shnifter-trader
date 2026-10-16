# Shnifter Risk-Helper Audit — 17 October 2026

## Defect and correction

The earlier get_portfolio_heat() returned **zero** if portfolio.balance <= 0,
even if the account had open trades. It also raised TypeError when a trade's
stop_loss was None. Either could make a safety gate wrongly show no risk.

The review version now returns positive infinity as a **fail-closed sentinel**
when available balance, trade quantity, entry price, stop or direction is
invalid, nonfinite, absent or inconsistent. A zero-trade account with valid
balance can still report zero nominal exposure. Valid long and short stops
remain compatible with existing stop-distance risk calculations.

check_drawdown() treats missing, NaN, infinite or invalid drawdown inputs as
a breached condition rather than a harmless no-op. The position-sizing
functions also reject boolean risk/cash inputs while allowing ordinary and
NumPy real-valued numerics.

The tests cover 11 cases, including normal long and short exposure, absent
stop levels, zero/negative equity, unknown direction, nonfinite drawdown,
NumPy scalars and confidence-independent cash risk budgets.

## Important limitations

- This is a deterministic **research / simulated-portfolio helper**. It
  does not enforce risk inside an IBKR or Alpaca account and has never been
  integrated with a live broker.
- Infinity is intended to cause an explicit *reject/halt* in a risk gate
  comparing exposure with an upper bound. Consumers that JSON-serialize,
  chart, or log this value need a deliberate unsafe-data representation.
- Stop-distance nominal loss is not maximum possible loss: price gaps,
  halted securities, margin, currency conversion and adverse fills can
  cause larger drawdowns.
- The numerator describes open trades' entry-to-stop price differences;
  it is not a portfolio expected shortfall model or a complete capital
  exposure check.
- Existing GUI and full repository integration still need testing.

No live trading enable flag or broker order path was changed.
