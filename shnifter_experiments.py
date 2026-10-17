"""Auditable, locally persistent Shnifter backtest experiment registry.

Stores the complete historical bars and the computed replay report, content
hashes both and independently recomputes results when recording/verifying.
No broker, GUI, LLM, network or remote filesystem action is available here.

SQLite triggers prevent normal UPDATE/DELETE. They are not a digital signature:
a process with filesystem ownership can replace the database and its triggers.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import asdict, fields
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from shnifter_replay import Bar, ReplayConfig, normalise_bars, run_replay

_SCHEMA_VERSION = "1"
_MAX_SOURCE_LENGTH = 160
_MAX_LIMIT = 500
_SCHEMA = """
CREATE TABLE registry_metadata (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
INSERT INTO registry_metadata (name, value) VALUES ('schema_version', '1');
CREATE TABLE experiments (
    experiment_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    ticker TEXT NOT NULL,
    engine TEXT NOT NULL,
    created_utc TEXT NOT NULL,
    declared_source TEXT NOT NULL,
    bar_count INTEGER NOT NULL CHECK (bar_count > 0),
    dataset_sha256 TEXT NOT NULL,
    report_sha256 TEXT NOT NULL,
    bars_json TEXT NOT NULL,
    report_json TEXT NOT NULL
);
CREATE INDEX idx_experiments_created ON experiments(created_utc,experiment_id);
CREATE TRIGGER no_experiment_changes BEFORE UPDATE ON experiments
BEGIN SELECT RAISE(ABORT,'experiments are immutable'); END;
CREATE TRIGGER no_experiment_deletes BEFORE DELETE ON experiments
BEGIN SELECT RAISE(ABORT,'experiments are immutable'); END;
"""


def _canonical(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _db_path(path: str | Path) -> Path:
    name = str(path)
    if not name or name == ":memory:":
        raise ValueError("registry requires a durable SQLite file path")
    p = Path(path)
    if p.is_dir():
        raise ValueError("registry path must be a file")
    if not p.parent.is_dir():
        raise ValueError("registry parent directory does not exist")
    # Prevent accidental modification of the legacy trading database.
    if p.name.lower() == "shnifter_trading.db":
        raise ValueError("refusing to use the existing Shnifter trading database")
    return p


def _assert_schema(conn: sqlite3.Connection) -> None:
    try:
        row = conn.execute(
            "SELECT value FROM registry_metadata WHERE name='schema_version'"
        ).fetchone()
        if row != (_SCHEMA_VERSION,):
            raise ValueError("registry schema version mismatch")
        conn.execute("SELECT experiment_id FROM experiments LIMIT 0")
    except sqlite3.Error as exc:
        raise ValueError("not a Shnifter experiment registry") from exc


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    path = _db_path(db_path)
    if not path.is_file():
        raise FileNotFoundError("experiment registry does not exist")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True,
                           timeout=5.0)
    try:
        _assert_schema(conn)
    except BaseException:
        conn.close()
        raise
    return conn


def _connect_write(db_path: str | Path) -> sqlite3.Connection:
    path = _db_path(db_path)
    existed = path.is_file() and path.stat().st_size > 0
    conn = sqlite3.connect(str(path), timeout=5.0)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        if existed:
            # Reject any nonempty DB that isn't already a Shnifter registry,
            # instead of silently adding tables to a user's other databases.
            _assert_schema(conn)
        else:
            # A single script retains the IMMEDIATE transaction while
            # creating all tables/triggers. executescript() itself commits any
            # transaction started *before* the script.
            conn.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA + "\nCOMMIT;")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn
    except BaseException:
        conn.close()
        raise


def _replay_config(settings: dict[str, Any]) -> ReplayConfig:
    if not isinstance(settings, dict):
        raise ValueError("replay settings must be an object")
    names = {f.name for f in fields(ReplayConfig)}
    if set(settings) != names:
        raise ValueError("replay setting keys mismatch")
    decimals = {key: Decimal(str(value)) for key, value in settings.items()
                if key not in ("fast_window", "slow_window")}
    cfg = ReplayConfig(**decimals,
                       fast_window=settings["fast_window"],
                       slow_window=settings["slow_window"])
    cfg.validate()
    return cfg


def _bars_snapshot(bars: Iterable[Bar]) -> tuple[list[Bar], str]:
    all_bars = list(bars)
    # Re-normalisation detects malformed data and nonchronological dates.
    clean = normalise_bars([asdict(b) for b in all_bars])
    snapshot = [{key: (str(value) if isinstance(value, Decimal) else value)
                 for key, value in asdict(bar).items()} for bar in clean]
    return clean, _canonical(snapshot)


def _calculate_artifact(bars: Iterable[Bar], report: dict[str, Any]):
    if not isinstance(report, dict) or not report.get("ok"):
        raise ValueError("only successful full replay reports can be recorded")
    clean, bars_json = _bars_snapshot(bars)
    cfg = _replay_config(report.get("settings"))
    ticker = report.get("ticker")
    if not isinstance(ticker, str) or not re.fullmatch(
        r"[A-Z0-9^][A-Z0-9.^_=-]{0,31}", ticker
    ):
        raise ValueError("invalid report ticker")
    actual = run_replay(clean, cfg, ticker=ticker)
    if _canonical(actual) != _canonical(report):
        raise ValueError("report differs from deterministic replay for these bars/settings")
    return bars_json, _canonical(actual)


def record_replay(db_path: str | Path, *, bars: Iterable[Bar],
                  report: dict[str, Any], declared_source: str = "unverified") -> dict:
    """Store a verified experiment idempotently. Never overwrite a different run.

    A declared source is user-supplied metadata, not proof that the data is real
    or point-in-time. Same report+bars+source yields same experiment_id.
    """
    if (not isinstance(declared_source, str) or
        not 1 <= len(declared_source) <= _MAX_SOURCE_LENGTH or
        any(ch in declared_source for ch in "\r\n\0")):
        raise ValueError("declared_source must be a short single-line string")
    bars_json, report_json = _calculate_artifact(bars, report)
    dataset_sha = _digest(bars_json)
    report_sha = _digest(report_json)
    identity = _canonical({"schema": _SCHEMA_VERSION, "bars": dataset_sha,
                           "report": report_sha, "source": declared_source})
    experiment_id = _digest(identity)
    db_path = _db_path(db_path)
    conn = _connect_write(db_path)
    try:
        with conn:
            conn.execute("INSERT OR IGNORE INTO experiments "
                         "(experiment_id,run_id,ticker,engine,created_utc,declared_source,"
                         "bar_count,dataset_sha256,report_sha256,bars_json,report_json) "
                         "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                         (experiment_id, report["run_id"], report["ticker"],
                          report["engine"], datetime.now(timezone.utc).isoformat(),
                          declared_source, report["bars"], dataset_sha,
                          report_sha, bars_json, report_json))
            row = conn.execute(
                "SELECT dataset_sha256,report_sha256,declared_source,bar_count,run_id "
                "FROM experiments WHERE experiment_id=?", (experiment_id,)
            ).fetchone()
            if row != (dataset_sha, report_sha, declared_source,
                       report["bars"], report["run_id"]):
                raise ValueError("stored experiment conflicts with computed identity")
            return {"ok": True, "experiment_id": experiment_id,
                    "run_id": report["run_id"], "bars": report["bars"],
                    "dataset_sha256": dataset_sha,
                    "report_sha256": report_sha,
                    "declared_source": declared_source}
    finally:
        conn.close()


def list_experiments(db_path: str | Path, *, limit: int = 20) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= _MAX_LIMIT:
        raise ValueError("limit must be an integer between 1 and 500")
    conn = _connect_readonly(db_path)
    try:
        records = conn.execute(
            "SELECT experiment_id,run_id,ticker,engine,created_utc,"
            "declared_source,bar_count,dataset_sha256,report_sha256 "
            "FROM experiments ORDER BY created_utc DESC,experiment_id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        fields_list = ("experiment_id", "run_id", "ticker", "engine", "created_utc",
                       "declared_source", "bars", "dataset_sha256", "report_sha256")
        return [dict(zip(fields_list, row)) for row in records]
    finally:
        conn.close()


def verify_experiment(db_path: str | Path, experiment_id: str) -> dict:
    if not isinstance(experiment_id, str) or not re.fullmatch(r"[0-9a-f]{64}", experiment_id):
        raise ValueError("experiment_id must be a 64-character lowercase SHA256")
    conn = _connect_readonly(db_path)
    try:
        row = conn.execute(
            "SELECT run_id,ticker,engine,declared_source,bar_count,dataset_sha256,"
            "report_sha256,bars_json,report_json FROM experiments WHERE experiment_id=?",
            (experiment_id,)
        ).fetchone()
        if row is None:
            raise ValueError("experiment not found")
        run_id, ticker, engine, source, count, data_sha, report_sha, bars_json, report_json = row
        issues = []
        if _digest(bars_json) != data_sha:
            issues.append("dataset content hash mismatch")
        if _digest(report_json) != report_sha:
            issues.append("report content hash mismatch")
        expected_identity = _digest(_canonical({"schema": _SCHEMA_VERSION,
                       "bars": data_sha, "report": report_sha, "source": source}))
        if experiment_id != expected_identity:
            issues.append("experiment identity mismatch")
        try:
            bar_rows = json.loads(bars_json)
            report = json.loads(report_json)
            if count != len(bar_rows) or report.get("bars") != count:
                issues.append("bar-count mismatch")
            if (report.get("run_id"), report.get("ticker"), report.get("engine")) != (
                run_id, ticker, engine
            ):
                issues.append("report metadata mismatch")
            from shnifter_replay import normalise_bars
            bars = normalise_bars(bar_rows)
            _calculate_artifact(bars, report)
        except Exception as exc:
            issues.append(f"replay mismatch: {exc}")
        return {"ok": not issues, "experiment_id": experiment_id,
                "run_id": run_id, "verification": "passed" if not issues else "failed",
                "issues": issues}
    finally:
        conn.close()
