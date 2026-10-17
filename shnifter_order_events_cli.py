"""Explicit local paper-event commands. No connection to a broker or live mode."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def _whole(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a nonnegative integer") from exc
    if not 0 <= number <= 10**12:
        raise argparse.ArgumentTypeError("integer out of bounds")
    return number


def register_order_events(subparsers) -> None:
    group = subparsers.add_parser("paper-events", help="Isolated event-sourced paper account; no live trading")
    commands = group.add_subparsers(dest="action", required=True)
    init = commands.add_parser("init", help="Create a NEW dedicated paper-events SQLite file")
    init.add_argument("--db", type=Path, required=True)
    init.add_argument("--initial-cash", default="10000")
    init.add_argument("--max-order-value", default="1000")
    init.add_argument("--max-total-value", default="5000")
    for name in ("status", "verify"):
        read = commands.add_parser(name, help="Rebuild and verify saved paper events without writing")
        read.add_argument("--db", type=Path, required=True)
    descriptions = {
        "submit": "Reserve a simulated LIMIT-order intent, without a fill",
        "transmit": "Record simulated transmission, without network activity",
        "ack": "Record an acknowledgement; no financial fill implied",
        "fill": "Record an EXPLICIT SIMULATED execution, partial or complete",
        "cancel-request": "Request simulated cancellation; sent orders keep reservations",
        "cancel-ack": "Record cancel acknowledgement; reconciliation still required",
        "reject": "Record simulated order rejection",
        "unknown": "Flag uncertain transmission outcome; do not resubmit",
        "reconcile": "Compare full simulated execution IDs/quantity before releasing reserves",
        "halt": "Persist a manual halt; no automatic reset command",
    }
    for name, description in descriptions.items():
        command = commands.add_parser(name, help=description)
        command.add_argument("--db", type=Path, required=True)
        command.add_argument("--event-id", required=True, help="Stable idempotency key; reuse only for the SAME event")
        if name != "halt":
            command.add_argument("--order-id", required=True)
        if name == "submit":
            command.add_argument("--ticker", required=True)
            command.add_argument("--side", choices=("BUY", "SELL"), required=True)
            command.add_argument("--quantity", type=_whole, required=True)
            command.add_argument("--limit-price", required=True)
            command.add_argument("--fee-budget", required=True, help="Maximum total simulated commission for the order")
        elif name == "fill":
            command.add_argument("--execution-id", required=True)
            command.add_argument("--quantity", type=_whole, required=True)
            command.add_argument("--price", required=True)
            command.add_argument("--fee", required=True, help="Explicit simulated commission on this fill")
        elif name == "reconcile":
            command.add_argument("--status", choices=("ACTIVE", "FILLED", "CANCELLED", "REJECTED"), required=True)
            command.add_argument("--filled-quantity", type=_whole, required=True)
            command.add_argument("--execution-ids", default="", help="Complete comma-separated execution IDs; empty for no fills")
        if name in ("halt", "unknown", "reject"):
            command.add_argument("--reason", required=True)


def run_order_events(args, *, stdout=None, stderr=None) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    try:
        from shnifter_order_events import PaperEventStore, cents
        if args.action == "init":
            result = PaperEventStore.create(args.db, initial_cash=args.initial_cash,
                max_order_value=args.max_order_value, max_total_value=args.max_total_value).status()
        else:
            store = PaperEventStore(args.db)
            if args.action in ("status", "verify"):
                result = getattr(store, args.action)()
            else:
                kind = args.action.upper().replace("-", "_")
                data = {"order_id": args.order_id} if args.action != "halt" else {}
                if args.action == "submit":
                    data.update(ticker=args.ticker.strip().upper(), side=args.side,
                        quantity=args.quantity, limit_cents=cents(args.limit_price, "limit_price"),
                        fee_budget_cents=cents(args.fee_budget, "fee_budget", zero=True))
                elif args.action == "fill":
                    data.update(execution_id=args.execution_id, quantity=args.quantity,
                        price_cents=cents(args.price, "price"), fee_cents=cents(args.fee, "fee", zero=True))
                elif args.action == "reconcile":
                    data.update(status=args.status, filled_quantity=args.filled_quantity,
                        execution_ids=args.execution_ids.split(",") if args.execution_ids else [])
                if args.action in ("halt", "unknown", "reject"):
                    data["reason"] = args.reason
                result = store.append(args.event_id, kind, data)
        out.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
        # 3 means event stored/account reconstructed but unresolved quarantine.
        return 0 if result["ok"] else 3
    except (OSError, ValueError, ArithmeticError, sqlite3.Error) as exc:
        err.write(json.dumps({"ok": False, "mode": "paper_events", "live_authorized": False,
                              "error": str(exc)}, allow_nan=False) + "\n")
        return 1
