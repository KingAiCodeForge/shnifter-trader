"""Shnifter Trader headless research CLI.

Read-only analysis by default, with explicit local SQLite research archiving.
Importing this module (including --help) does not load Qt, an LLM or a broker.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import math
import re
import sys
from datetime import date
from pathlib import Path
from typing import Callable, Sequence

FIELDS = ("open", "high", "low", "close", "adj_close", "volume")
REQUIRED_FIELDS = ("open", "high", "low", "close", "volume")


def _ticker(value: str) -> str:
    ticker = value.strip().upper()
    # One ticker per request. No whitespace, option injection, or arbitrary paths.
    if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.^_=-]{0,31}", ticker):
        raise argparse.ArgumentTypeError(
            "expected one ticker (for example AAPL, BRK-B, ^GSPC or EURUSD=X)"
        )
    return ticker


def _iso_date(value: str) -> date:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise argparse.ArgumentTypeError("expected a date in YYYY-MM-DD format")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("invalid calendar date") from exc


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="shnifter-trader",
        description="Headless research and opt-in experiment registry; no order routing.",
    )
    groups = parser.add_subparsers(dest="group", required=True)
    market = groups.add_parser("market", help="Market-data commands")
    market_actions = market.add_subparsers(dest="action", required=True)

    history = market_actions.add_parser(
        "historical", help="Fetch daily historical OHLCV data; no trades are placed"
    )
    history.add_argument("--ticker", type=_ticker, required=True, help="One symbol")
    history.add_argument("--start", type=_iso_date, required=True, help="Inclusive YYYY-MM-DD")
    history.add_argument("--end", type=_iso_date, required=True, help="Exclusive YYYY-MM-DD")
    history.add_argument(
        "--provider", choices=("yfinance",), default="yfinance",
        help="Only the connected yfinance price provider is currently supported",
    )
    history.add_argument(
        "--limit", type=_positive_int, default=100,
        help="Most recent N returned rows (default: 100)",
    )
    history.add_argument("--format", choices=("json", "csv"), default="json")
    history.add_argument("--output", type=Path, help="Write to file instead of stdout")
    history.add_argument(
        "--overwrite", action="store_true",
        help="Permit replacing an existing --output file",
    )
    # Second read-only action: historical replay, no simulated/live account writes.
    from shnifter_backtest_cli import register_backtest
    register_backtest(groups.add_parser("backtest", help="Deterministic historical strategy replay"))
    from shnifter_agent_cli import register_actions
    register_actions(groups)
    from shnifter_experiment_cli import register_experiment_cli
    register_experiment_cli(groups)
    from shnifter_research_cli import register_research
    register_research(groups)
    return parser


def _fetch_historical(ticker: str, start: str, end: str):
    """Reuse the same ShnifterBB data path as the GUI.

    Existing platform code prints init/debug messages. Route those to stderr so
    JSON/CSV on stdout stays machine-readable.
    """
    with contextlib.redirect_stdout(sys.stderr):
        from shnifterBB.shnifter_bb import ShnifterBB

        return ShnifterBB().equity.price.historical(
            ticker, start_date=start, end_date=end
        ).to_df()


def _canonical_field(value: object) -> str:
    return str(value).strip().lower().replace(" ", "_")


def _column_map(frame) -> dict[str, object]:
    columns: dict[str, object] = {}
    for original in frame.columns:
        # yfinance can return either flat fields or (field, ticker) MultiIndex
        # tuples. Never stringify the tuple as a field name.
        candidates = original if isinstance(original, tuple) else (original,)
        canonical = next(
            (name for candidate in candidates
             if (name := _canonical_field(candidate)) in FIELDS),
            None,
        )
        if canonical is None:
            continue
        if canonical in columns:
            raise ValueError(f"ambiguous duplicate price column: {canonical}")
        columns[canonical] = original
    missing = set(REQUIRED_FIELDS).difference(columns)
    if missing:
        raise ValueError("missing required OHLCV columns: " + ", ".join(sorted(missing)))
    return columns


def _numeric(value, field: str):
    # NaN and infinite numbers are not valid JSON; represent missing prices
    # and adjusted closes as null rather than inventing a value.
    if value is None:
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError(f"non-numeric {field} value: {value!r}") from exc
    if not math.isfinite(number):
        return None
    if field == "volume":
        if not number.is_integer():
            raise ValueError("volume must contain whole units")
        return int(number)
    return number


def _records_from_frame(frame, limit: int) -> list[dict]:
    if frame is None or frame.empty:
        raise ValueError("no historical prices returned for the requested symbol/dates")
    columns = _column_map(frame)
    selected = frame.sort_index().tail(limit)
    records = []
    for timestamp, row in selected.iterrows():
        # Historical is daily data; retain the exchange-date label.
        if hasattr(timestamp, "date"):
            stamp = timestamp.date().isoformat()
        elif hasattr(timestamp, "isoformat"):
            stamp = timestamp.isoformat()
        else:
            stamp = str(timestamp)
        record = {"date": stamp}
        for field in FIELDS:
            record[field] = (
                _numeric(row[columns[field]], field) if field in columns else None
            )
        records.append(record)
    return records


def _serialize(rows: list[dict], meta: dict, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(
            {"ok": True, **meta, "count": len(rows), "rows": rows},
            indent=2, ensure_ascii=False, allow_nan=False,
        ) + "\n"
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=("date", *FIELDS))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def main(
    argv: Sequence[str] | None = None,
    *,
    fetcher: Callable[[str, str, str], object] | None = None,
    stdout=None,
    stderr=None,
) -> int:
    """Return 0 for success, 1 for runtime errors, 2 for invalid date ranges.

    A fetcher can be injected for deterministic offline testing. No broker,
    simulated execution, GUI or LLM operation is reachable from these actions.
    """
    args = build_parser().parse_args(argv)
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if args.group == "backtest":
        from shnifter_backtest_cli import execute_backtest
        return execute_backtest(args, stdout=out, stderr=err)
    if args.group == "experiments":
        from shnifter_experiment_cli import run_experiment_cli
        return run_experiment_cli(args, stdout=out, stderr=err)
    if args.group == "research":
        from shnifter_research_cli import run_research
        return run_research(args, stdout=out, stderr=err)
    if args.group in ("analysis", "actions"):
        from shnifter_agent_cli import run_action
        return run_action(args, stdout=out, stderr=err)

    if args.start >= args.end:
        print("error: --start must be earlier than --end (end is exclusive)", file=err)
        return 2
    if args.overwrite and args.output is None:
        print("error: --overwrite requires --output", file=err)
        return 2

    try:
        source = fetcher if fetcher is not None else _fetch_historical
        frame = source(args.ticker, args.start.isoformat(), args.end.isoformat())
        rows = _records_from_frame(frame, args.limit)
        meta = {
            "action": "market.historical",
            "provider": args.provider,
            "ticker": args.ticker,
            "start": args.start.isoformat(),
            "end_exclusive": args.end.isoformat(),
        }
        document = _serialize(rows, meta, args.format)
        if args.output is None:
            out.write(document)
        else:
            mode = "w" if args.overwrite else "x"
            with args.output.open(mode, encoding="utf-8", newline="") as handle:
                handle.write(document)
            out.write(json.dumps({
                "ok": True,
                "action": "market.historical",
                "output": str(args.output),
                "format": args.format,
                "count": len(rows),
            }) + "\n")
        return 0
    except Exception as exc:
        print(f"shnifter-trader: market historical failed: {exc}", file=err)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
