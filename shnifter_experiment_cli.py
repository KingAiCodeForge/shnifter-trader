"""Command-line read-only registry queries. Recording is explicit in backtest run."""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


def register_experiment_cli(subparsers) -> None:
    parser = subparsers.add_parser("experiments", help="Inspect immutable local backtest runs")
    actions = parser.add_subparsers(dest="action", required=True)
    listed = actions.add_parser("list", help="List recorded experiments from SQLite")
    listed.add_argument("--registry-db", type=Path, required=True)
    listed.add_argument("--limit", type=int, default=20)
    verified = actions.add_parser("verify", help="Verify saved hashes and replay result")
    verified.add_argument("--registry-db", type=Path, required=True)
    verified.add_argument("--id", required=True)


def run_experiment_cli(args, *, stdout=None, stderr=None) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    try:
        from shnifter_experiments import list_experiments, verify_experiment
        if args.action == "list":
            result = {"ok": True, "experiments": list_experiments(
                args.registry_db, limit=args.limit)}
        elif args.action == "verify":
            result = verify_experiment(args.registry_db, args.id)
        else:
            raise ValueError("unsupported experiment command")
        out.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
        return 0 if result["ok"] else 1
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        err.write(f"shnifter-trader: experiment command failed: {exc}\n")
        return 1
