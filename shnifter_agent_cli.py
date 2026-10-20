"""New research CLI command registrations for the existing shnifter_cli.py."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path


def register_actions(parser):
    tool = parser.add_parser("actions", help="Agent-accessible read-only tool catalogue")
    sub = tool.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="List machine-callable research actions as JSON")
    analysis = parser.add_parser("analysis", help="Headless trading-signal research")
    ops = analysis.add_subparsers(dest="action", required=True)
    signal = ops.add_parser("signals", help="Calculate signals from chronological daily CSV")
    signal.add_argument("--csv", type=Path, required=True)
    signal.add_argument("--ticker", required=True)
    signal.add_argument("--fast", type=int, default=20)
    signal.add_argument("--slow", type=int, default=50)
    signal.add_argument("--min-labeled", type=int, default=80)
    signal.add_argument("--no-ml", action="store_true")
    signal.add_argument("--output", type=Path)
    signal.add_argument("--overwrite", action="store_true")


def run_action(args, *, stdout=None, stderr=None) -> int:
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    if args.group == 'actions':
        from shnifter_actions import invoke_action
        out.write(json.dumps(invoke_action('actions.list'), indent=2) + '\n')
        return 0
    if args.group != 'analysis':
        raise ValueError("expected actions or analysis group")
    if args.overwrite and args.output is None:
        err.write('error: --overwrite requires --output\n')
        return 2
    try:
        from shnifter_safe_output import validate_output, atomic_write_text
        if args.output is not None:
            validate_output(args.output, overwrite=args.overwrite, protected=(args.csv,))
        from shnifter_actions import invoke_action
        from shnifter_replay import load_csv
        result = invoke_action('analysis.signals', {
            'rows': [asdict(b) for b in load_csv(args.csv)],
            'ticker': args.ticker, 'fast': args.fast, 'slow': args.slow,
            'min_labeled': args.min_labeled, 'use_ml': not args.no_ml,
        })
        text = json.dumps(result, indent=2, allow_nan=False) + '\n'
        if args.output is None:
            out.write(text)
        else:
            atomic_write_text(args.output, text, overwrite=args.overwrite,
                              protected=(args.csv,))
            out.write(json.dumps({'ok': True, 'action': 'analysis.signals',
                                  'output': str(args.output)}) + '\n')
        return 0
    except Exception as exc:
        err.write(f'shnifter-trader: analysis failed: {exc}\n')
        return 1
