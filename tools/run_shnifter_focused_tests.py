#!/usr/bin/env python3
"""Run explicit offline suites and record exact source hashes and actual results.

This is NOT the full repository suite or a security sandbox. Missing files,
source mismatches, test failures, zero tests and timeouts cannot become PASS.
The caller explicitly chooses a new local output directory. No GitHub Actions.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    "research": ["test_shnifter_cli.py", "test_shnifter_replay.py", "test_shnifter_backtest_cli.py",
                 "test_shnifter_agent_interfaces.py", "test_shnifter_experiments.py",
                 "test_shnifter_oos_gate.py", "test_shnifter_research_integrity.py"],
    "paper": ["test_shnifter_paper_ledger.py", "test_shnifter_paper_cli.py"],
    "lifecycle": ["test_shnifter_order_events.py", "test_shnifter_order_events_cli.py",
                  "test_shnifter_lifecycle_boundaries.py", "test_shnifter_checkpoint.py"],
    "runner": ["test_shnifter_focused_runner.py"],
}


def source_hashes(root: Path, files: list[str]) -> dict:
    result = {}
    for relative in sorted(set(files)):
        path = root / relative
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"missing/unsafe source path: {relative}")
        blob = path.read_bytes()
        result[relative] = {"sha256": hashlib.sha256(blob).hexdigest(),
                            "git_blob_sha1": hashlib.sha1(b"blob " + str(len(blob)).encode() + b"\0" + blob).hexdigest(),
                            "bytes": len(blob)}
    return result


def junit_counts(path: Path) -> dict:
    xml = ET.parse(path).getroot()
    nodes = [xml] if xml.tag == "testsuite" else list(xml.findall("testsuite"))
    return {key: sum(int(n.get(key, "0")) for n in nodes)
            for key in ("tests", "failures", "errors", "skipped")}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["focused", *SUITES], default="focused")
    parser.add_argument("--output-dir", type=Path, required=True, help="Must NOT already exist")
    parser.add_argument("--expected-manifest", type=Path,
                        help="JSON with sources mapping to sha256; mismatch stops before running")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 900:
        parser.error("timeout must be 1..900 seconds")
    names = sum(SUITES.values(), []) if args.suite == "focused" else SUITES[args.suite]
    files = ["tests/" + name for name in names]
    started = time.monotonic()
    receipt = {"ok": False, "scope": args.suite, "full_repository_suite": False,
               "live_authorized": False, "python": sys.version, "test_files": files,
               "limitations": ["No GUI, installed wheel, Windows, MCP host or broker account validation",
                               "Synthetic prices; passing tests are not trading profitability"]}
    try:
        args.output_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        return 2
    try:
        expected = {}
        if args.expected_manifest:
            manifest = json.loads(args.expected_manifest.read_text(encoding="utf-8"))
            expected = manifest["sources"]
            if not isinstance(expected, dict) or not expected:
                raise ValueError("expected manifest must name nonempty sources")
            receipt["base_commit"] = manifest.get("base_commit")
        runtime = [p.name for p in ROOT.glob("shnifter*.py") if p.is_file()]
        hashes = source_hashes(ROOT, files + runtime + list(expected) + ["tools/run_shnifter_focused_tests.py"])
        receipt["sources"] = hashes
        for path, spec in expected.items():
            if hashes[path]["sha256"] != spec["sha256"]:
                raise ValueError(f"source differs from expected manifest: {path}")
        receipt["expected_hashes_matched"] = bool(expected)
        packages = {}
        for name in ("pytest", "numpy", "pandas", "scikit-learn", "fastapi", "httpx"):
            try:
                packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:
                packages[name] = None
        receipt["packages"] = packages
        xml = (args.output_dir / "junit.xml").resolve()
        cmd = [sys.executable, "-m", "pytest", "-q", "--disable-warnings",
               "--junitxml=" + str(xml), *files]
        receipt["command"] = cmd
        env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD="1", PYTEST_ADDOPTS="")
        result = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=args.timeout)
        (args.output_dir / "pytest.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        counts = junit_counts(xml)
        after = source_hashes(ROOT, list(hashes))
        unchanged = hashes == after
        passed = re.search(r"\b(\d+) passed(?:,| in)", result.stdout)
        subtests = re.search(r"\b(\d+) subtests passed", result.stdout)
        receipt.update(exit_code=result.returncode, counts=counts,
                       counts_include_subtests=True, sources_unchanged=unchanged,
                       passed_test_methods=int(passed.group(1)) if passed else None,
                       passed_subtests=int(subtests.group(1)) if subtests else None)
        receipt["ok"] = (result.returncode == 0 and counts["tests"] > 0 and unchanged and
                         not any(counts[k] for k in ("failures", "errors", "skipped")))
    except (ValueError, KeyError, OSError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        receipt["error"] = str(exc)
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 3)
    (args.output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": receipt["ok"], "receipt": str(args.output_dir / "receipt.json"),
                      "counts": receipt.get("counts"), "error": receipt.get("error")}, indent=2))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
