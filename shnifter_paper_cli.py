"""Local, isolated paper-ledger CLI. All actions are simulated/offline.

No broker connection, live order adapter or secret/account credentials are used.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


def _decimal(value: str) -> Decimal:
    try:
        x = Decimal(value)
    except (ValueError, InvalidOperation) as exc:
        raise argparse.ArgumentTypeError('expected decimal number') from exc
    if not x.is_finite():
        raise argparse.ArgumentTypeError('decimal must be finite')
    return x


def _whole(value: str) -> int:
    try:
        x = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('expected integer') from exc
    if x < 0:
        raise argparse.ArgumentTypeError('quantity must be nonnegative')
    return x


def register_paper(parser: argparse.ArgumentParser) -> None:
    actions = parser.add_subparsers(dest='action', required=True)
    init = actions.add_parser('init', help='Create isolated simulated account database')
    init.add_argument('--db', required=True, type=Path)
    init.add_argument('--initial-cash', type=_decimal, default=Decimal('10000'))
    init.add_argument('--max-position-pct', type=_decimal, default=Decimal('0.20'))
    init.add_argument('--max-realised-loss-pct', type=_decimal, default=Decimal('0.05'))
    init.add_argument('--max-signal-age-minutes', type=_whole, default=120)
    init.add_argument('--fee-bps', type=_decimal, default=Decimal(10))
    init.add_argument('--slippage-bps', type=_decimal, default=Decimal(5))

    status = actions.add_parser('status', help='Read stored cash/positions (not real market value)')
    status.add_argument('--db', required=True, type=Path)

    order = actions.add_parser('order', help='Simulate a whole-share paper fill (never a live order)')
    order.add_argument('--db', required=True, type=Path)
    order.add_argument('--event-key', required=True, help='Stable, unique strategy/bar/action key')
    order.add_argument('--ticker', required=True)
    order.add_argument('--side', choices=['BUY', 'SELL', 'HOLD'], required=True)
    order.add_argument('--quantity', type=_whole, required=True)
    order.add_argument('--price', type=_decimal, required=True,
                       help='Explicit simulated reference price; not sourced from market')
    order.add_argument('--source-at', required=True,
                       help='ISO 8601 quote/signal datetime WITH UTC offset; max age enforced')
    order.add_argument('--position-id', help='Required for SELL; exact saved position ID')

    halt = actions.add_parser('halt', help='Permanently disable new paper entries')
    halt.add_argument('--db', required=True, type=Path)
    halt.add_argument('--reason', required=True)


def execute_paper(args, *, stdout=None, stderr=None) -> int:
    from shnifter_paper_ledger import PaperLedger, PaperPolicy

    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    try:
        if args.action == 'init':
            if args.db.exists() and args.db.stat().st_size:
                raise ValueError('database already exists; use paper status; never reset implicitly')
            policy = PaperPolicy(
                initial_cash=args.initial_cash,
                max_position_pct=args.max_position_pct,
                max_realised_loss_pct=args.max_realised_loss_pct,
                max_signal_age_minutes=args.max_signal_age_minutes,
                fee_bps=args.fee_bps,
                slippage_bps=args.slippage_bps,
            )
            result = PaperLedger(args.db, policy).status()
        else:
            ledger = PaperLedger.open_existing(args.db)
            if args.action == 'status':
                result = ledger.status()
            elif args.action == 'halt':
                result = ledger.halt(args.reason)
            elif args.action == 'order':
                result = ledger.submit(
                    event_key=args.event_key, ticker=args.ticker, side=args.side,
                    quantity=args.quantity, price=args.price,
                    source_at=args.source_at, position_id=args.position_id,
                )
            else:
                raise ValueError('unknown paper action')
        out.write(json.dumps(result, allow_nan=False, indent=2) + '\n')
        return 0 if result.get('ok') else 1
    except Exception as exc:
        print(f'shnifter-trader: paper {args.action} failed: {exc}', file=err)
        return 1
