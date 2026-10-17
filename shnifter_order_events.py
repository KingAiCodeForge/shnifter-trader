"""Small, event-sourced PAPER order lifecycle. No broker, network, LLM or live mode.

A LIMIT-order accounting simulator, not a matching engine. Fills are explicit
simulation inputs. Cash/shares remain reserved through UNKNOWN and cancellation
until reconciliation. Late contradictions are quarantined, never invented away.
Only the append-only log is persisted; each transaction reconstructs its state.
Entry admission stops at 10,000 events, but safety/reconciliation events remain
recordable. Full replay is intended only for small local research accounts.
Version 2 refuses v1 stores; no silent migration or live broker approval.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

VERSION = "shnifter.paper-events.v2"
APPLICATION_ID = 0x53485045
MAX_EVENTS = 10000  # New-entry admission limit, NOT a kill-switch/write limit.
MAX_INTEGER = 10**12
ZERO_HASH = "0" * 64
TERMINAL = {"FILLED", "CANCELLED", "REJECTED"}
KINDS = {"SUBMIT", "TRANSMIT", "ACK", "FILL", "CANCEL_REQUEST", "CANCEL_ACK",
         "REJECT", "UNKNOWN", "RECONCILE", "HALT"}


class IntegrityError(ValueError):
    """The saved event stream or an idempotency identity is inconsistent."""


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def identifier(value: Any, name: str) -> str:
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise ValueError(f"{name} must be a 1..128 character identifier")
    return value


def integer(value: Any, name: str, *, zero: bool = False) -> int:
    if type(value) is not int or not (0 if zero else 1) <= value <= MAX_INTEGER:
        raise ValueError(f"{name} must be a bounded {'nonnegative' if zero else 'positive'} integer")
    return value


def cents(value: Any, name: str, *, zero: bool = False) -> int:
    """Reject fractional cents rather than silently change financial inputs."""
    if type(value) not in (int, float, str, Decimal):
        raise ValueError(f"{name} must be decimal money")
    try:
        val = Decimal(str(value))
        if not val.is_finite() or val < 0 or val > Decimal(MAX_INTEGER) / 100:
            raise ValueError(f"invalid {name}")
        scaled = val * 100
        if scaled != scaled.to_integral_value():
            raise ValueError(f"{name} must have at most two decimal places")
        return integer(int(scaled), name, zero=zero)
    except (InvalidOperation, OverflowError) as exc:
        raise ValueError(f"invalid {name}") from exc


def fields(data: Any, required: set[str]) -> None:
    if type(data) is not dict or set(data) != required:
        raise ValueError(f"expected exactly these fields: {sorted(required)}")


def _reason(value: Any) -> str:
    if type(value) is not str or not 1 <= len(value.strip()) <= 240 or any(ord(c) < 32 for c in value):
        raise ValueError("reason must be 1..240 printable characters")
    return value


def _reserved(state: dict) -> tuple[int, dict[str, int]]:
    money, units = 0, {}
    for order in state["orders"].values():
        if order["settled"]:
            continue
        left = order["quantity"] - order["filled_quantity"]
        if order["side"] == "BUY":
            money += left * order["limit_cents"] + order["fee_budget_cents"] - order["fees_cents"]
        else:
            symbol = order["ticker"]
            units[symbol] = units.get(symbol, 0) + left
    return money, units


def _invariants(state: dict) -> None:
    reserve, units = _reserved(state)
    cash = state["cash_cents"]
    cost = sum(p["cost_cents"] for p in state["positions"].values())
    if cash < 0 or reserve < 0 or reserve > cash:
        raise IntegrityError("cash/reservation invariant failed")
    if cash + cost != state["initial_cents"] + state["realised_pnl_cents"]:
        raise IntegrityError("cash + position cost != initial cash + realised P&L")
    for ticker, position in state["positions"].items():
        if (position["quantity"] < 0 or position["cost_cents"] < 0 or
                (position["quantity"] == 0 and position["cost_cents"] != 0) or
                units.get(ticker, 0) > position["quantity"]):
            raise IntegrityError("position/reservation invariant failed")
    if any(t not in state["positions"] and q for t, q in units.items()):
        raise IntegrityError("reserved shares have no position")


def _needs_reconciliation(state: dict) -> bool:
    """One authoritative predicate for both displayed state and admission."""
    return bool(state["quarantine"] or any(
        order["uncertain"] or (order["status"] in TERMINAL and not order["settled"])
        for order in state["orders"].values()))


def _entry_capacity(state: dict | None, kind: str, data: dict, count: int) -> None:
    """At the research capacity limit, forbid new BUY risk, not account cleanup.

    Existing fills, acknowledgements, cancellations, halts, reconciliation and
    bounded closing SELL intentions remain recordable. This does not make full
    replay scalable; retire the account after a reconciled wind-down.
    """
    if count < MAX_EVENTS or state is None or type(data) is not dict:
        return
    side = data.get("side") if kind == "SUBMIT" else None
    if kind == "TRANSMIT":
        oid = data.get("order_id")
        if type(oid) is str:
            side = state["orders"].get(oid, {}).get("side")
    if kind in ("SUBMIT", "TRANSMIT") and side == "BUY":
        raise ValueError("entry capacity reached; only cleanup and closing sales remain available")


def _quarantine(state: dict, event_id: str, message: str) -> dict:
    state["quarantine"].append({"event_id": event_id, "reason": message})
    return state


def reduce_event(before: dict | None, event_id: str, kind: str, data: dict) -> dict:
    """Pure public reducer: preserve the caller's entire snapshot."""
    return _apply_event(copy.deepcopy(before), event_id, kind, data)


def _apply_event(before: dict | None, event_id: str, kind: str, data: dict) -> dict:
    """Apply to a PRIVATE projection owned by this replay/transaction.

    Never publish this object before successful replay/COMMIT. Avoid repeatedly
    copying the entire growing account when reconstructing thousands of events.
    Public callers use reduce_event(), which retains copy isolation.
    """
    identifier(event_id, "event_id")
    if before is None:
        if kind != "INIT":
            raise IntegrityError("first event must initialise the account")
        fields(data, {"initial_cents", "max_order_cents", "max_total_cents"})
        for key, value in data.items():
            integer(value, key)
        if not data["max_order_cents"] <= data["max_total_cents"] <= data["initial_cents"]:
            raise ValueError("require order cap <= aggregate cost cap <= initial cash")
        return {**data, "cash_cents": data["initial_cents"], "realised_pnl_cents": 0,
                "orders": {}, "positions": {}, "executions": {},
                "manual_halt": False, "halt_reason": None, "quarantine": []}
    if type(kind) is not str or kind not in KINDS:
        raise ValueError("unsupported paper event")
    state = before  # Private projection; discard it if any event fails.
    if kind == "HALT":
        fields(data, {"reason"})
        state.update(manual_halt=True, halt_reason=_reason(data["reason"]))
        return state
    if kind == "SUBMIT":
        fields(data, {"order_id", "ticker", "side", "quantity", "limit_cents", "fee_budget_cents"})
        oid = identifier(data["order_id"], "order_id")
        ticker = data["ticker"]
        if type(ticker) is not str or not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,15}", ticker):
            raise ValueError("only a single uppercase equity symbol is supported")
        if data["side"] not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        qty = integer(data["quantity"], "quantity")
        price = integer(data["limit_cents"], "limit_cents")
        fee = integer(data["fee_budget_cents"], "fee_budget_cents", zero=True)
        if oid in state["orders"]:
            raise ValueError("order_id already exists; retry its original event_id")
        if _needs_reconciliation(state):
            raise ValueError("account requires reconciliation; new intentions blocked")
        if sum(not o["settled"] for o in state["orders"].values()) >= 128:
            raise ValueError("too many unresolved paper orders")
        reserved, reserved_shares = _reserved(state)
        if data["side"] == "BUY":
            cost = qty * price + fee
            if state["manual_halt"]:
                raise ValueError("manual halt blocks new entries")
            if cost > state["max_order_cents"]:
                raise ValueError("order cost cap exceeded")
            if cost > state["cash_cents"] - reserved:
                raise ValueError("insufficient unreserved paper cash")
            held_cost = sum(p["cost_cents"] for p in state["positions"].values())
            if held_cost + reserved + cost > state["max_total_cents"]:
                raise ValueError("aggregate deployed-cost cap exceeded")
        else:
            held = state["positions"].get(ticker, {}).get("quantity", 0)
            if qty > held - reserved_shares.get(ticker, 0):
                raise ValueError("sell exceeds unreserved long shares")
        state["orders"][oid] = {**data, "status": "NEW", "filled_quantity": 0,
                                "fees_cents": 0, "settled": False,
                                "transmitted": False, "cancel_requested": False, "uncertain": False,
                                "execution_ids": []}
        _invariants(state)
        return state
    extra = {"FILL": {"execution_id", "quantity", "price_cents", "fee_cents"},
             "RECONCILE": {"status", "filled_quantity", "execution_ids"},
             "REJECT": {"reason"}, "UNKNOWN": {"reason"}}.get(kind, set())
    fields(data, {"order_id"} | extra)
    oid = identifier(data["order_id"], "order_id")
    if oid not in state["orders"]:
        raise ValueError("unknown order_id; explicit intent must precede delivery")
    order = state["orders"][oid]
    if kind in {"UNKNOWN", "REJECT"}:
        _reason(data["reason"])
    if kind == "TRANSMIT":
        if order["status"] != "NEW" or order["transmitted"]:
            raise ValueError("only a NEW intent can be marked transmitted; no auto-retry")
        # Admission at SUBMIT is not a permanent licence: state may change
        # while an intention is waiting to transmit. Do not block delivery of
        # actual fills for orders that had ALREADY been transmitted.
        if _needs_reconciliation(state):
            raise ValueError("account requires reconciliation; transmission blocked")
        if order["side"] == "BUY" and state["manual_halt"]:
            raise ValueError("manual halt blocks staged entry transmission")
        _invariants(state)
        order.update(status="PENDING_SUBMIT", transmitted=True)
    elif kind == "ACK":
        if not order["transmitted"]:
            raise ValueError("cannot acknowledge an untransmitted intent")
        # A delayed acknowledgement cannot regress PARTIAL, cancellation or UNKNOWN.
        if order["status"] == "PENDING_SUBMIT":
            order["status"] = "ACKNOWLEDGED"
    elif kind == "CANCEL_REQUEST":
        if order["settled"] or order["status"] in TERMINAL:
            raise ValueError("order is already terminal")
        if not order["transmitted"]:
            order.update(status="CANCELLED", settled=True)
        else:
            order.update(status="CANCEL_PENDING", cancel_requested=True)
    elif kind == "CANCEL_ACK":
        if not order["transmitted"] or not order["cancel_requested"]:
            raise ValueError("cancellation acknowledgement requires a sent cancel request")
        if not order["settled"]:
            # Keep reservations until a complete execution reconciliation follows.
            order["status"] = "CANCELLED"
    elif kind == "UNKNOWN":
        if not order["transmitted"] or order["settled"]:
            raise ValueError("uncertainty requires an unresolved transmitted order")
        order["status"] = "UNKNOWN"
        order["uncertain"] = True
    elif kind == "REJECT":
        if order["filled_quantity"] or order["settled"]:
            return _quarantine(state, event_id, "rejection contradicts recorded fills/terminal state")
        order["status"] = "REJECTED"
        order["settled"] = not order["transmitted"]
    elif kind == "FILL":
        eid = identifier(data["execution_id"], "execution_id")
        qty = integer(data["quantity"], "quantity")
        price = integer(data["price_cents"], "price_cents")
        fee = integer(data["fee_cents"], "fee_cents", zero=True)
        if eid in state["executions"]:
            if state["executions"][eid] != data:
                return _quarantine(state, event_id, "execution_id reused with different fill details")
            return state  # Same execution delivered in a different wrapper message.
        if order["settled"] or not order["transmitted"]:
            return _quarantine(state, event_id, "new fill contradicts settled/untransmitted order")
        if qty > order["quantity"] - order["filled_quantity"]:
            return _quarantine(state, event_id, "fill exceeds remaining order quantity")
        if order["fees_cents"] + fee > order["fee_budget_cents"]:
            return _quarantine(state, event_id, "fill exceeds reserved fee budget")
        if ((order["side"] == "BUY" and price > order["limit_cents"]) or
                (order["side"] == "SELL" and price < order["limit_cents"])):
            return _quarantine(state, event_id, "fill violates simulated limit price")
        if order["side"] == "SELL" and fee > qty * price:
            return _quarantine(state, event_id, "sell commission exceeds proceeds")
        ticker = order["ticker"]
        position = state["positions"].setdefault(ticker, {"quantity": 0, "cost_cents": 0})
        if order["side"] == "BUY":
            cost = qty * price + fee
            state["cash_cents"] -= cost
            position["quantity"] += qty
            position["cost_cents"] += cost
        else:
            if qty > position["quantity"]:
                return _quarantine(state, event_id, "sell fill exceeds recorded holdings")
            # Integer average-cost allocation; final sale removes all remaining cost.
            basis = position["cost_cents"] * qty // position["quantity"]
            proceeds = qty * price - fee
            state["cash_cents"] += proceeds
            state["realised_pnl_cents"] += proceeds - basis
            position["quantity"] -= qty
            position["cost_cents"] -= basis
        state["executions"][eid] = copy.deepcopy(data)
        order["execution_ids"].append(eid)
        order["filled_quantity"] += qty
        order["fees_cents"] += fee
        if order["filled_quantity"] == order["quantity"]:
            order.update(status="FILLED", settled=True, uncertain=False)
        elif order["status"] not in ("UNKNOWN", "CANCEL_PENDING", "CANCELLED", "REJECTED"):
            order["status"] = "PARTIAL"
    elif kind == "RECONCILE":
        target = data["status"]
        if target not in ("ACTIVE", "FILLED", "CANCELLED", "REJECTED"):
            raise ValueError("invalid reconciliation status")
        integer(data["filled_quantity"], "filled_quantity", zero=True)
        reported = data["execution_ids"]
        if type(reported) is not list or len(reported) > 10000:
            raise ValueError("execution_ids must be a bounded list")
        for eid in reported:
            identifier(eid, "execution_id")
        if len(reported) != len(set(reported)):
            raise ValueError("duplicate execution IDs in reconciliation")
        if (data["filled_quantity"] != order["filled_quantity"] or
                set(reported) != set(order["execution_ids"])):
            return _quarantine(state, event_id, "reconciliation has missing/conflicting executions")
        if (not order["transmitted"] or
                (order["settled"] and target != order["status"]) or
                (target == "FILLED") != (order["filled_quantity"] == order["quantity"]) or
                (target == "REJECTED" and order["filled_quantity"])):
            return _quarantine(state, event_id, "reconciliation contradicts lifecycle state")
        order["status"] = ("PARTIAL" if order["filled_quantity"] else "ACKNOWLEDGED") if target == "ACTIVE" else target
        order["settled"] = target != "ACTIVE"
        order["uncertain"] = False
        if target == "ACTIVE":
            order["cancel_requested"] = False
    _invariants(state)
    return state


_SCHEMA = """
CREATE TABLE metadata (version TEXT NOT NULL);
CREATE TABLE events (seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL, payload_json TEXT NOT NULL,
    previous_hash TEXT NOT NULL, event_hash TEXT NOT NULL);
CREATE TRIGGER events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'event log is append-only'); END;
CREATE TRIGGER events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'event log is append-only'); END;
"""


def _path(value: str | Path) -> Path:
    path = Path(value)
    if (str(value) in ("", ":memory:") or path.is_symlink() or
            path.name.lower() == "shnifter_trading.db"):
        raise ValueError("use a dedicated, non-symlink paper-events database")
    if not path.parent.is_dir():
        raise ValueError("database parent must already exist")
    return path


class PaperEventStore:
    """One isolated local paper account. Not interchangeable with old ledgers."""
    def __init__(self, path: str | Path):
        self.path = _path(path)
        if not self.path.is_file():
            raise FileNotFoundError("paper-events database does not exist; initialise explicitly")

    @classmethod
    def create(cls, path: str | Path, *, initial_cash="10000", max_order_value="1000",
               max_total_value="5000") -> "PaperEventStore":
        path = _path(path)
        data = {"initial_cents": cents(initial_cash, "initial_cash"),
                "max_order_cents": cents(max_order_value, "max_order_value"),
                "max_total_cents": cents(max_total_value, "max_total_value")}
        reduce_event(None, "genesis", "INIT", data)  # Validate before touching disk.
        # Never initialise an existing database or add tables to another service.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        try:
            with closing(sqlite3.connect(path, isolation_level=None)) as db:
                db.execute("PRAGMA synchronous=FULL")
                db.execute(f"PRAGMA application_id={APPLICATION_ID}")
                db.executescript("BEGIN IMMEDIATE;\n" + _SCHEMA)
                db.execute("INSERT INTO metadata VALUES (?)", (VERSION,))
                cls._insert(db, 1, "genesis", {"kind": "INIT", "data": data}, ZERO_HASH)
                db.execute("COMMIT")
        except BaseException:
            # An interrupted init remains a non-reusable invalid file; no implicit reset.
            raise
        return cls(path)

    def _connect(self, *, write: bool = False) -> sqlite3.Connection:
        path = _path(self.path)
        db = sqlite3.connect(path.resolve().as_uri() + ("?mode=rw" if write else "?mode=ro"),
                             uri=True, isolation_level=None, timeout=5)
        try:
            if db.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
                raise IntegrityError("not a Shnifter paper-events database")
            if db.execute("SELECT version FROM metadata").fetchall() != [(VERSION,)]:
                raise IntegrityError("paper-events schema/reducer version mismatch")
            db.execute("PRAGMA synchronous=FULL")
        except BaseException:
            db.close()
            raise
        return db

    @staticmethod
    def _insert(db, seq: int, event_id: str, payload: dict, previous: str) -> str:
        recorded = datetime.now(timezone.utc).isoformat()
        text = canonical(payload)
        event_hash = digest([seq, event_id, recorded, text, previous])
        db.execute("INSERT INTO events VALUES (?,?,?,?,?,?)",
                   (seq, event_id, recorded, text, previous, event_hash))
        return event_hash

    @staticmethod
    def _load(db) -> tuple[dict, int, str]:
        state, count, previous = None, 0, ZERO_HASH
        for seq, eid, at, text, prev, hashed in db.execute(
                "SELECT seq,event_id,recorded_at,payload_json,previous_hash,event_hash "
                "FROM events ORDER BY seq"):
            count += 1
            try:
                if (seq != count or prev != previous or
                        digest([seq, eid, at, text, prev]) != hashed):
                    raise IntegrityError("broken sequence or event hash chain")
                if type(text) is not str or len(text.encode("utf-8")) > 65536:
                    raise IntegrityError("invalid or oversized event envelope")
                payload = json.loads(text)
                if (type(payload) is not dict or set(payload) != {"kind", "data"}
                        or canonical(payload) != text):
                    raise IntegrityError("noncanonical event envelope")
                _entry_capacity(state, payload["kind"], payload["data"], count - 1)
                state = _apply_event(state, eid, payload["kind"], payload["data"])
            except (ValueError, TypeError, KeyError, ArithmeticError, RecursionError) as exc:
                raise IntegrityError(f"invalid stored event at sequence {count}: {exc}") from exc
            previous = hashed
        if state is None:
            raise IntegrityError("missing initialisation event")
        _invariants(state)
        return state, count, previous

    def append(self, event_id: str, kind: str, data: dict) -> dict:
        identifier(event_id, "event_id")
        if type(kind) is not str or kind not in KINDS:
            raise ValueError("unsupported paper event")
        if type(data) is not dict:
            raise ValueError("event data must be an object")
        payload = {"kind": kind, "data": data}
        text = canonical(payload)
        if len(text.encode("utf-8")) > 65536:
            raise ValueError("event payload too large")
        with closing(self._connect(write=True)) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                state, count, prev = self._load(db)
                old = db.execute("SELECT payload_json,event_hash FROM events WHERE event_id=?", (event_id,)).fetchone()
                if old:
                    if old[0] != text:
                        raise IntegrityError("event_id reused with different content")
                    result = self._receipt(state, count, prev)
                    result.update(duplicate=True, event_id=event_id, recorded_event_hash=old[1])
                else:
                    _entry_capacity(state, kind, data, count)
                    state = reduce_event(state, event_id, kind, data)
                    hashed = self._insert(db, count + 1, event_id, payload, prev)
                    result = self._receipt(state, count + 1, hashed)
                    result.update(duplicate=False, event_id=event_id, recorded_event_hash=hashed)
                db.execute("COMMIT")
                return result
            except BaseException:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                raise

    @staticmethod
    def _receipt(state: dict, count: int, head: str) -> dict:
        reserve, units = _reserved(state)
        reasons = []
        if state["manual_halt"]:
            reasons.append("manual_halt")
        if _needs_reconciliation(state):
            reasons.append("unreconciled_state")
        if count >= MAX_EVENTS:
            reasons.append("event_admission_limit")
        return {"ok": not state["quarantine"], "mode": "paper_events", "engine": VERSION,
                "live_authorized": False, "event_count": count, "head_hash": head,
                "state_sha256": digest(state), "reserved_cash_cents": reserve,
                "available_cash_cents": state["cash_cents"] - reserve,
                "reserved_shares": units,
                "requires_reconciliation": _needs_reconciliation(state),
                "new_entries_allowed": not reasons, "entry_block_reasons": reasons,
                "entry_admission_limit": MAX_EVENTS, **state,
                "notes": "Explicit simulated fills; cash/cost basis are not marked-to-market NAV"}

    def status(self) -> dict:
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            state, count, head = self._load(db)
            return self._receipt(state, count, head)

    def verify(self) -> dict:
        result = self.status()
        return {key: result[key] for key in
                ("ok", "mode", "engine", "live_authorized", "event_count", "head_hash",
                 "state_sha256", "manual_halt", "quarantine")}
