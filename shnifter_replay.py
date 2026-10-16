"""Deterministic, long-only SMA-crossover paper backtesting.

Signals use a *completed* daily close; orders fill at the NEXT bar's open.
There is no broker access, no LLM confidence and no synthetic performance data.
This is a research simulator, not proof of a profitable strategy.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable, Mapping


MONEY = Decimal('0.01')


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _num(value: object, name: str, *, positive: bool = False) -> Decimal:
    try:
        number = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f'{name} must be numeric') from exc
    if not number.is_finite() or (positive and number <= 0):
        raise ValueError(f'{name} must be finite' + (' and > 0' if positive else ''))
    return number


@dataclass(frozen=True)
class Bar:
    date: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


def normalise_bars(rows: Iterable[Mapping[str, object]]) -> list[Bar]:
    bars: list[Bar] = []
    previous: str | None = None
    for row in rows:
        try:
            day = date.fromisoformat(str(row['date']))
            day_str = day.isoformat()
            values = {field: _num(row[field], field, positive=field != 'volume')
                      for field in ('open', 'high', 'low', 'close', 'volume')}
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f'invalid historical row {len(bars) + 1}: {exc}') from exc
        if values['volume'] < 0:
            raise ValueError('volume must be non-negative')
        if values['high'] < max(values['open'], values['close'], values['low']):
            raise ValueError(f'{day_str}: high below open/close/low')
        if values['low'] > min(values['open'], values['close']):
            raise ValueError(f'{day_str}: low above open/close')
        if previous is not None and day_str <= previous:
            raise ValueError('dates must be strictly increasing and unique')
        previous = day_str
        bars.append(Bar(day_str, **values))
    if not bars:
        raise ValueError('no historical bars supplied')
    return bars


def load_csv(path: str | Path) -> list[Bar]:
    with Path(path).open('r', newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        required = {'date', 'open', 'high', 'low', 'close', 'volume'}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError('CSV must include date,open,high,low,close,volume columns')
        return normalise_bars(reader)


def from_dataframe(frame) -> list[Bar]:
    """Convert yfinance flat or MultiIndex OHLCV DataFrame; no Qt imports."""
    if frame is None or frame.empty:
        raise ValueError('no history returned')
    fields = {}
    for col in frame.columns:
        candidates = col if isinstance(col, tuple) else (col,)
        for name in candidates:
            norm = str(name).strip().lower()
            if norm in ('open', 'high', 'low', 'close', 'volume'):
                if norm in fields:
                    raise ValueError(f'ambiguous duplicate column: {norm}')
                fields[norm] = col
                break
    missing = set(('open', 'high', 'low', 'close', 'volume')) - fields.keys()
    if missing:
        raise ValueError(f'missing OHLCV columns: {sorted(missing)}')
    # Normalisation rejects duplicate or unsorted days instead of silently fixing
    # chronology; downstream results must be reproducible.
    rows = []
    for stamp, row in frame.iterrows():
        rows.append({'date': str(stamp.date() if hasattr(stamp, 'date') else stamp)[:10],
                     **{name: row[col] for name, col in fields.items()}})
    return normalise_bars(rows)


@dataclass(frozen=True)
class ReplayConfig:
    initial_cash: Decimal = Decimal('10000')
    fast_window: int = 20
    slow_window: int = 50
    max_position_pct: Decimal = Decimal('0.20')
    fee_bps: Decimal = Decimal('10')
    slippage_bps: Decimal = Decimal('5')
    stop_loss_pct: Decimal = Decimal('0.05')
    take_profit_pct: Decimal = Decimal('0.10')
    max_drawdown_pct: Decimal = Decimal('0.20')

    def validate(self):
        if not isinstance(self.fast_window, int) or not isinstance(self.slow_window, int):
            raise ValueError('SMA windows must be integers')
        if not 1 <= self.fast_window < self.slow_window:
            raise ValueError('expected 1 <= fast_window < slow_window')
        if _num(self.initial_cash, 'initial_cash', positive=True) <= 0:
            raise ValueError('invalid initial cash')
        for field in ('max_position_pct', 'stop_loss_pct', 'take_profit_pct', 'max_drawdown_pct'):
            value = _num(getattr(self, field), field, positive=True)
            if value >= 1:
                raise ValueError(f'{field} must be below 1')
        for field in ('fee_bps', 'slippage_bps'):
            value = _num(getattr(self, field), field)
            if value < 0 or value >= 10000:
                raise ValueError(f'{field} must be in [0,10000)')


def _fee(notional: Decimal, cfg: ReplayConfig) -> Decimal:
    return _money(notional * cfg.fee_bps / Decimal('10000'))


def _fill_price(price: Decimal, side: str, cfg: ReplayConfig) -> Decimal:
    sign = Decimal('1') if side == 'BUY' else Decimal('-1')
    return _money(price * (1 + sign * cfg.slippage_bps / Decimal('10000')))


def _float(v: Decimal) -> float:
    return float(_money(v))


def run_replay(bars: Iterable[Bar], cfg: ReplayConfig | None = None, *, ticker: str = 'UNKNOWN') -> dict:
    """Replay strictly ordered OHLCV, producing real simulated fills and audit data.

    One instrument, long only, whole shares. Signals at close (SMA crossover),
    entries/exits at next open, protective stops/targets intraday. On bars where
    both stop and target are hit, the stop has conservative precedence.
    """
    cfg = cfg or ReplayConfig()
    cfg.validate()
    prices = list(bars)
    if not prices or len(prices) <= cfg.slow_window:
        raise ValueError('not enough historical bars for a crossover backtest')
    if prices != normalise_bars([asdict(b) for b in prices]):
        raise ValueError('invalid input bars')
    if not ticker or not isinstance(ticker, str):
        raise ValueError('ticker required')

    fingerprint = json.dumps({
        'config': {k: str(v) for k, v in asdict(cfg).items()},
        'ticker': ticker.upper(),
        'prices': [[str(v) for v in asdict(b).values()] for b in prices],
        'version': 1,
    }, sort_keys=True, separators=(',', ':')).encode()
    run_id = hashlib.sha256(fingerprint).hexdigest()[:24]

    cash = _money(cfg.initial_cash)
    peak = cash
    high_water_drawdown = Decimal('0')
    open_trade: dict | None = None
    pending: str | None = None
    disabled = False
    trades: list[dict] = []
    fills: list[dict] = []
    signals: list[dict] = []
    equity_curve: list[dict] = []
    closes: list[Decimal] = []
    prev_fast: Decimal | None = None
    prev_slow: Decimal | None = None
    for i, bar in enumerate(prices):
        if pending == 'EXIT' and open_trade is not None:
            side = 'SELL'
            fill = _fill_price(bar.open, side, cfg)
            qty = open_trade['qty']
            cost = _fee(fill * qty, cfg)
            cash += fill * qty - cost
            pnl = (fill - open_trade['entry']) * qty - open_trade['entry_fee'] - cost
            fills.append({'id': f'{run_id}-F{len(fills)+1:05}', 'date': bar.date,
                          'side': side, 'reason': 'crossover', 'qty': qty,
                          'price': _float(fill), 'fee': _float(cost)})
            trades.append({'id': open_trade['id'], 'ticker': ticker.upper(),
                           'entry_date': open_trade['date'], 'exit_date': bar.date,
                           'qty': qty, 'entry': _float(open_trade['entry']),
                           'exit': _float(fill), 'pnl': _float(pnl),
                           'exit_reason': 'crossover'})
            open_trade = None
        elif pending == 'ENTRY' and open_trade is None and not disabled:
            fill = _fill_price(bar.open, 'BUY', cfg)
            budget = min(cash, _money(cash * cfg.max_position_pct))
            # Include entry fees within the affordability limit.
            qty = int(budget / (fill * (1 + cfg.fee_bps / Decimal('10000'))))
            if qty > 0:
                cost = _fee(fill * qty, cfg)
                if fill * qty + cost > cash:
                    raise RuntimeError('position sizing violated cash invariant')
                cash -= fill * qty + cost
                fills.append({'id': f'{run_id}-F{len(fills)+1:05}', 'date': bar.date,
                              'side': 'BUY', 'reason': 'crossover', 'qty': qty,
                              'price': _float(fill), 'fee': _float(cost)})
                open_trade = {'id': f'{run_id}-T{len(fills):05}', 'date': bar.date,
                              'entry': fill, 'entry_fee': cost, 'qty': qty,
                              'stop': _money(fill * (1 - cfg.stop_loss_pct)),
                              'target': _money(fill * (1 + cfg.take_profit_pct))}
        pending = None

        # Protective orders: gaps execute no better than actual opening price;
        # if both levels hit on the same bar, assume the worst (stop first).
        if open_trade is not None:
            reason = None
            if bar.low <= open_trade['stop']:
                trigger = min(bar.open, open_trade['stop'])
                reason = 'stop'
            elif bar.high >= open_trade['target']:
                trigger = max(bar.open, open_trade['target'])
                reason = 'target'
            if reason:
                fill = _fill_price(trigger, 'SELL', cfg)
                qty = open_trade['qty']
                cost = _fee(fill * qty, cfg)
                cash += fill * qty - cost
                pnl = (fill - open_trade['entry']) * qty - open_trade['entry_fee'] - cost
                fills.append({'id': f'{run_id}-F{len(fills)+1:05}', 'date': bar.date,
                              'side': 'SELL', 'reason': reason, 'qty': qty,
                              'price': _float(fill), 'fee': _float(cost)})
                trades.append({'id': open_trade['id'], 'ticker': ticker.upper(),
                               'entry_date': open_trade['date'], 'exit_date': bar.date,
                               'qty': qty, 'entry': _float(open_trade['entry']),
                               'exit': _float(fill), 'pnl': _float(pnl),
                               'exit_reason': reason})
                open_trade = None

        equity = cash + (open_trade['qty'] * bar.close if open_trade else 0)
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak
        high_water_drawdown = max(high_water_drawdown, drawdown)
        if drawdown >= cfg.max_drawdown_pct and not disabled:
            disabled = True
            signals.append({'date': bar.date, 'decision': 'HALT',
                            'reason': 'drawdown limit breached; no new entries'})
            if open_trade is not None:
                pending = 'EXIT'
        equity_curve.append({'date': bar.date, 'equity': _float(equity),
                             'cash': _float(cash), 'drawdown_pct': round(float(drawdown * 100), 4)})

        # Current bar closes before these SMA values can be known.
        closes.append(bar.close)
        if len(closes) >= cfg.slow_window:
            fast = sum(closes[-cfg.fast_window:]) / cfg.fast_window
            slow = sum(closes[-cfg.slow_window:]) / cfg.slow_window
            if prev_fast is not None and prev_slow is not None and i < len(prices) - 1:
                if prev_fast <= prev_slow and fast > slow and open_trade is None and not disabled:
                    pending = 'ENTRY'
                    signals.append({'date': bar.date, 'decision': 'BUY', 'execution': 'next_open'})
                elif prev_fast >= prev_slow and fast < slow and open_trade is not None:
                    pending = 'EXIT'
                    signals.append({'date': bar.date, 'decision': 'SELL', 'execution': 'next_open'})
            prev_fast, prev_slow = fast, slow

    final_equity = cash + (open_trade['qty'] * prices[-1].close if open_trade else 0)
    wins = sum(t['pnl'] > 0 for t in trades)
    total = len(trades)
    realised = sum((Decimal(str(t['pnl'])) for t in trades), Decimal('0'))
    unrealised = ((prices[-1].close - open_trade['entry']) * open_trade['qty']
                  - open_trade['entry_fee']) if open_trade else Decimal('0')
    return {
        'ok': True, 'engine': 'shnifter.sma.next-open.v1', 'run_id': run_id,
        'ticker': ticker.upper(), 'first_date': prices[0].date,
        'last_date': prices[-1].date, 'bars': len(prices),
        'settings': {k: (str(v) if isinstance(v, Decimal) else v)
                     for k, v in asdict(cfg).items()},
        'initial_cash': _float(cfg.initial_cash), 'cash': _float(cash),
        'final_equity': _float(final_equity),
        'total_return_pct': round(float((final_equity / cfg.initial_cash - 1) * 100), 5),
        'realised_pnl': _float(realised), 'unrealised_pnl': _float(unrealised),
        'max_drawdown_pct': round(float(high_water_drawdown * 100), 5),
        'completed_trades': total,
        'win_rate_pct': round(wins / total * 100, 4) if total else None,
        'halted': disabled, 'open_position': ({
            'trade_id': open_trade['id'], 'qty': open_trade['qty'],
            'entry': _float(open_trade['entry']), 'entry_date': open_trade['date']
        } if open_trade else None),
        'signals': signals, 'fills': fills, 'trades': trades,
        'equity_curve': equity_curve,
        'assumptions': ['Daily OHLCV only, no live broker',
                        'SMA decisions at completed close, fills at next open',
                        'Conservative stop-before-target if both hit same bar',
                        'Single symbol, long only, whole shares, no borrowing',
                        'Fixed adverse slippage and proportional fees',
                        'No market-impact, liquidity or dividend model',
                        'Open positions marked at last close, not forcibly liquidated'],
    }
