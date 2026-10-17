"""Headless CLI wiring for deterministic offline historical replay."""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


def _decimal(value: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError('expected a decimal number') from exc
    if not number.is_finite():
        raise argparse.ArgumentTypeError('expected a finite decimal number')
    return number


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('expected a positive integer') from exc
    if number <= 0:
        raise argparse.ArgumentTypeError('expected a positive integer')
    return number


def register_backtest(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest='action', required=True)
    command = actions.add_parser('run', help='Replay historical daily OHLCV, no orders')
    command.add_argument('--csv', type=Path, required=True,
                         help='CSV with date,open,high,low,close,volume')
    command.add_argument('--ticker', required=True)
    command.add_argument('--fast', type=_positive_int, default=20)
    command.add_argument('--slow', type=_positive_int, default=50)
    command.add_argument('--initial-cash', type=_decimal, default=Decimal('10000'))
    command.add_argument('--max-position-pct', type=_decimal, default=Decimal('0.20'))
    command.add_argument('--max-drawdown-pct', type=_decimal, default=Decimal('0.20'))
    command.add_argument('--stop-loss-pct', type=_decimal, default=Decimal('0.05'))
    command.add_argument('--take-profit-pct', type=_decimal, default=Decimal('0.10'))
    command.add_argument('--fee-bps', type=_decimal, default=Decimal('10'))
    command.add_argument('--slippage-bps', type=_decimal, default=Decimal('5'))
    command.add_argument('--registry-db', type=Path,
                         help='Explicitly record a verified replay in a separate SQLite file')
    command.add_argument('--declared-source', default='unverified',
                         help='Unverified user-supplied data provenance label')
    command.add_argument('--output', type=Path, help='JSON report output path')
    command.add_argument('--overwrite', action='store_true',
                         help='Explicitly replace existing output file')


def execute_backtest(args, *, stdout=None, stderr=None) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if args.overwrite and args.output is None:
        print('error: --overwrite requires --output', file=err)
        return 2
    if args.registry_db is None and args.declared_source != 'unverified':
        print('error: --declared-source requires --registry-db', file=err)
        return 2
    try:
        from shnifter_safe_output import validate_output, atomic_write_text
        protected = [args.csv]
        if args.registry_db is not None:
            validate_output(args.registry_db, overwrite=True, protected=(args.csv,))
            protected.extend([args.registry_db, str(args.registry_db) + '-wal',
                              str(args.registry_db) + '-shm'])
        if args.output is not None:
            validate_output(args.output, overwrite=args.overwrite, protected=protected)
        from shnifter_replay import ReplayConfig, load_csv, run_replay

        config = ReplayConfig(
            initial_cash=args.initial_cash, fast_window=args.fast,
            slow_window=args.slow, max_position_pct=args.max_position_pct,
            max_drawdown_pct=args.max_drawdown_pct,
            stop_loss_pct=args.stop_loss_pct, take_profit_pct=args.take_profit_pct,
            fee_bps=args.fee_bps, slippage_bps=args.slippage_bps,
        )
        ticker = args.ticker.strip().upper()
        if not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^_=-]{0,31}', ticker):
            raise ValueError('ticker must be a single symbol of at most 32 characters')
        bars = load_csv(args.csv)
        result = run_replay(bars, config, ticker=ticker)
        if args.registry_db is not None:
            from shnifter_experiments import record_replay
            recorded = record_replay(args.registry_db, bars=bars, report=result,
                                     declared_source=args.declared_source)
            print(f"Experiment registered: {recorded['experiment_id']}", file=err)
        output = json.dumps(result, indent=2, allow_nan=False) + '\n'
        if args.output is None:
            out.write(output)
        else:
            atomic_write_text(args.output, output, overwrite=args.overwrite,
                              protected=protected)
            out.write(json.dumps({
                'ok': True, 'action': 'backtest.run',
                'path': str(args.output), 'run_id': result['run_id'],
                'completed_trades': result['completed_trades'],
                'total_return_pct': result['total_return_pct'],
            }) + '\n')
        return 0
    except Exception as exc:
        print(f'shnifter-trader: backtest run failed: {exc}', file=err)
        return 1
