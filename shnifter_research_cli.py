"""Headless chronological strategy screening commands (research-only)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path


def decimal_arg(value: str) -> Decimal:
    try:
        num = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("expected decimal") from exc
    if not num.is_finite():
        raise argparse.ArgumentTypeError("expected finite decimal")
    return num


def positive_int(value: str) -> int:
    try:
        n = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected positive integer") from exc
    if n <= 0:
        raise argparse.ArgumentTypeError("expected positive integer")
    return n


def parse_pairs(value: str) -> tuple[tuple[int, int], ...]:
    parts = value.split(",")
    if not 1 <= len(parts) <= 12:
        raise argparse.ArgumentTypeError("candidates must contain 1..12 SMA fast:slow pairs")
    pairs = []
    for pair in parts:
        if not re.fullmatch(r"\d{1,3}:\d{1,3}", pair):
            raise argparse.ArgumentTypeError("expected comma-separated SMA fast:slow pairs")
        fast, slow = (int(v) for v in pair.split(":"))
        if not 2 <= fast < slow <= 250:
            raise argparse.ArgumentTypeError("expected 2 <= fast < slow <= 250")
        if (fast, slow) in pairs:
            raise argparse.ArgumentTypeError("duplicate candidate")
        pairs.append((fast, slow))
    return tuple(pairs)


def register_research(subparsers) -> None:
    research = subparsers.add_parser("research", help="Independent historical research checks")
    actions = research.add_subparsers(dest="action", required=True)
    gate = actions.add_parser("gate", help="Walk-forward OOS SMA comparison; NOT live approval")
    gate.add_argument("--csv", type=Path, required=True)
    gate.add_argument("--ticker", required=True)
    gate.add_argument("--folds", type=positive_int, default=3)
    gate.add_argument("--validation-bars", type=positive_int, default=80)
    gate.add_argument("--test-bars", type=positive_int, default=80)
    gate.add_argument("--min-prior-bars", type=positive_int, default=150)
    gate.add_argument("--fee-bps", type=decimal_arg, default=Decimal("10"))
    gate.add_argument("--slippage-bps", type=decimal_arg, default=Decimal("5"))
    gate.add_argument("--stress-multiplier", type=decimal_arg, default=Decimal("2"))
    gate.add_argument("--max-position-pct", type=decimal_arg, default=Decimal("0.20"))
    gate.add_argument("--initial-cash", type=decimal_arg, default=Decimal("10000"))
    gate.add_argument("--min-trades", type=positive_int, default=4)
    gate.add_argument("--min-excess-return-pct", type=decimal_arg, default=Decimal("1"))
    gate.add_argument("--max-test-drawdown-pct", type=decimal_arg, default=Decimal("20"))
    gate.add_argument("--candidates", type=parse_pairs,
                      default=((5,20),(10,30),(20,50),(20,100)))
    gate.add_argument("--summary-only", action="store_true",
                      help="Omit fold detail from JSON; decisions and identifiers are unchanged")
    gate.add_argument("--fail-on-rejection", action="store_true",
                      help="Return exit 3 when screening rejects the candidate (not a runtime error)")
    gate.add_argument("--output", type=Path)
    gate.add_argument("--overwrite", action="store_true")


def run_research(args, *, stdout=None, stderr=None) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if args.action != "gate":
        print("unsupported research action", file=err)
        return 2
    if args.overwrite and args.output is None:
        print("--overwrite requires --output", file=err)
        return 2
    try:
        from shnifter_safe_output import validate_output, atomic_write_text
        if args.output is not None:
            validate_output(args.output, overwrite=args.overwrite, protected=(args.csv,))
        from shnifter_replay import load_csv
        from shnifter_oos_gate import evaluate_oos, GatePolicy
        policy = GatePolicy(
            folds=args.folds, validation_bars=args.validation_bars,
            test_bars=args.test_bars, min_prior_bars=args.min_prior_bars,
            fee_bps=args.fee_bps, slippage_bps=args.slippage_bps,
            stress_multiplier=args.stress_multiplier,
            max_position_pct=args.max_position_pct, initial_cash=args.initial_cash,
            min_total_completed_trades=args.min_trades,
            min_mean_excess_return_pct=args.min_excess_return_pct,
            max_test_drawdown_pct=args.max_test_drawdown_pct,
            candidates=args.candidates)
        ticker=args.ticker.strip().upper()
        if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^_=-]{0,31}",ticker):
            raise ValueError("ticker must be a valid single symbol")
        report = evaluate_oos(load_csv(args.csv), ticker=ticker, policy=policy)
        if args.summary_only:
            report = {key: value for key, value in report.items() if key != "folds"}
            report["detail_level"] = "summary"
        data = json.dumps(report, indent=2, allow_nan=False) + "\n"
        if args.output is None:
            out.write(data)
        else:
            atomic_write_text(args.output, data, overwrite=args.overwrite,
                              protected=(args.csv,))
            out.write(json.dumps({"ok":True,"output":str(args.output),
                                  "evaluation_id":report["evaluation_id"],
                                  "paper_candidate":report["summary"]["paper_research_candidate"],
                                  "live_authorized":False})+"\n")
        if args.fail_on_rejection and not report["summary"]["paper_research_candidate"]:
            return 3
        return 0
    except (ValueError, ArithmeticError, OSError) as exc:
        print(f"shnifter-trader: research gate failed: {exc}", file=err)
        return 1
