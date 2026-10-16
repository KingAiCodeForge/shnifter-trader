"""Restart-safe SQLite paper-only accounting; no brokers or live order paths.

This is a new, isolated database schema: NEVER point it at the legacy
shnifter_trading.db. Every paper fill and cash change is one SQLite transaction.
The default policy allows one long stock position and bounded allocations.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


CENT = Decimal('0.01')


def _cents(value, label, positive=False):
    try:
        v = Decimal(str(value))
    except Exception as exc:
        raise ValueError(f'{label} must be decimal') from exc
    if not v.is_finite() or (positive and v <= 0) or v < 0:
        raise ValueError(f'{label} must be finite and nonnegative' + (' (>0)' if positive else ''))
    cents = (v * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(cents)


def _dollars(cents):
    return float(Decimal(cents) / 100)


def _utc(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('signal time must be ISO 8601 with timezone')
    return value.astimezone(timezone.utc)


def _id(namespace, event_key):
    return hashlib.sha256((namespace + ':' + event_key).encode('utf-8')).hexdigest()[:32]


@dataclass(frozen=True)
class PaperPolicy:
    initial_cash: Decimal = Decimal('10000')
    max_position_pct: Decimal = Decimal('0.20')
    max_realised_loss_pct: Decimal = Decimal('0.05')
    fee_bps: Decimal = Decimal('10')
    slippage_bps: Decimal = Decimal('5')
    max_signal_age_minutes: int = 120

    def validate(self):
        if _cents(self.initial_cash, 'initial_cash', positive=True) < 1:
            raise ValueError('initial cash must be >= $0.01')
        for field in ('max_position_pct', 'max_realised_loss_pct'):
            value = Decimal(str(getattr(self, field)))
            if not value.is_finite() or value <= 0 or value >= 1:
                raise ValueError(f'{field} must be between 0 and 1 (exclusive)')
        for field in ('fee_bps', 'slippage_bps'):
            value = Decimal(str(getattr(self, field)))
            if not value.is_finite() or value < 0 or value >= 10000:
                raise ValueError(f'{field} must be between 0 and 10000 bps')
        if not isinstance(self.max_signal_age_minutes, int) or self.max_signal_age_minutes <= 0:
            raise ValueError('max_signal_age_minutes must be positive')


SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS paper_account (
  id INTEGER PRIMARY KEY CHECK(id=1), cash_cents INTEGER NOT NULL,
  initial_cents INTEGER NOT NULL, halted INTEGER NOT NULL DEFAULT 0,
  halt_reason TEXT
);
CREATE TABLE IF NOT EXISTS paper_policy (
  id INTEGER PRIMARY KEY CHECK(id=1), settings_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_signals (
  signal_id TEXT PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
  payload_hash TEXT NOT NULL, created_at TEXT NOT NULL,
  source_at TEXT NOT NULL, ticker TEXT NOT NULL,
  side TEXT NOT NULL CHECK(side IN ('BUY','SELL','HOLD')),
  quantity INTEGER NOT NULL, expected_price_cents INTEGER NOT NULL,
  position_id TEXT, status TEXT NOT NULL, reason TEXT
);
CREATE TABLE IF NOT EXISTS paper_positions (
  position_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, quantity INTEGER NOT NULL,
  entry_cents INTEGER NOT NULL, entry_fee_cents INTEGER NOT NULL,
  exit_cents INTEGER, exit_fee_cents INTEGER, realised_pnl_cents INTEGER,
  opened_at TEXT NOT NULL, closed_at TEXT,
  status TEXT NOT NULL CHECK(status IN ('OPEN','CLOSED'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_open_ticker ON paper_positions(ticker)
  WHERE status='OPEN';
CREATE TABLE IF NOT EXISTS paper_orders (
  order_id TEXT PRIMARY KEY, signal_id TEXT NOT NULL UNIQUE,
  side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
  quantity INTEGER NOT NULL, status TEXT NOT NULL CHECK(status='FILLED'),
  created_at TEXT NOT NULL,
  FOREIGN KEY(signal_id) REFERENCES paper_signals(signal_id)
);
CREATE TABLE IF NOT EXISTS paper_fills (
  fill_id TEXT PRIMARY KEY, order_id TEXT NOT NULL UNIQUE,
  signal_id TEXT NOT NULL UNIQUE,
  position_id TEXT NOT NULL, side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
  quantity INTEGER NOT NULL, fill_cents INTEGER NOT NULL,
  fee_cents INTEGER NOT NULL, created_at TEXT NOT NULL,
  FOREIGN KEY(order_id) REFERENCES paper_orders(order_id),
  FOREIGN KEY(signal_id) REFERENCES paper_signals(signal_id),
  FOREIGN KEY(position_id) REFERENCES paper_positions(position_id)
);
'''


class PaperLedger:
    @classmethod
    def open_existing(cls, db_path: str | Path):
        """Load the persisted risk policy without accepting new safety limits."""
        path = Path(db_path)
        if not path.is_file():
            raise FileNotFoundError('paper ledger not initialized; use paper init')
        with closing(sqlite3.connect(str(path))) as db:
            row = db.execute('SELECT settings_json FROM paper_policy WHERE id=1').fetchone()
        if not row:
            raise ValueError('paper database is missing its policy')
        stored = json.loads(row[0])
        cfg = {key: (int(value) if key == 'max_signal_age_minutes' else Decimal(value))
               for key, value in stored.items()}
        return cls(path, PaperPolicy(**cfg))

    def __init__(self, db_path: str | Path, policy: PaperPolicy | None = None):
        self.path = Path(db_path)
        if self.path.name == 'shnifter_trading.db':
            raise ValueError('refusing legacy database; choose a new paper-only path')
        self.policy = policy or PaperPolicy()
        self.policy.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript(SCHEMA)
            db.execute('INSERT OR IGNORE INTO paper_account(id,cash_cents,initial_cents) VALUES (1,?,?)',
                       (_cents(self.policy.initial_cash, 'initial_cash'),
                        _cents(self.policy.initial_cash, 'initial_cash')))
            row = db.execute('SELECT initial_cents FROM paper_account WHERE id=1').fetchone()
            if row[0] != _cents(self.policy.initial_cash, 'initial_cash'):
                raise ValueError('existing ledger has a different starting balance')
            policy_json = json.dumps({name: str(getattr(self.policy, name))
                                      for name in self.policy.__dataclass_fields__},
                                     sort_keys=True)
            db.execute('INSERT OR IGNORE INTO paper_policy(id,settings_json) VALUES(1,?)',
                       (policy_json,))
            actual = db.execute('SELECT settings_json FROM paper_policy WHERE id=1').fetchone()[0]
            if actual != policy_json:
                raise ValueError('paper policy differs from stored immutable risk settings')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(str(self.path), timeout=20)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA busy_timeout=20000')
            db.execute('PRAGMA foreign_keys=ON')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _receipt(self, db, event_key, duplicate=False):
        signal = dict(db.execute(
            'SELECT signal_id,event_key,ticker,side,quantity,status,reason,position_id '
            'FROM paper_signals WHERE event_key=?', (event_key,)).fetchone())
        fill = db.execute('SELECT fill_id,order_id,quantity,fill_cents,fee_cents FROM paper_fills '
                          'WHERE signal_id=?', (signal['signal_id'],)).fetchone()
        signal['duplicate'] = duplicate
        signal['fill'] = ({'id':fill['fill_id'], 'order_id':fill['order_id'], 'quantity':fill['quantity'],
                           'price':_dollars(fill['fill_cents']),
                           'fee':_dollars(fill['fee_cents'])} if fill else None)
        signal['ok'] = signal['status'] != 'REJECTED'
        return signal

    def submit(self, *, event_key: str, ticker: str, side: str, quantity: int,
               price, source_at, position_id: str | None = None, now=None):
        """Atomically record one paper signal and (if accepted) its whole-share fill.

        Event key must be unique to strategy/symbol/bar/decision. Repeated key and
        same payload returns the previous receipt without executing again.
        Close positions ONLY by exact position_id; no ticker-wide UPDATE.
        """
        if not isinstance(event_key, str) or not 1 <= len(event_key) <= 160:
            raise ValueError('event_key must be 1..160 characters')
        ticker = str(ticker).strip().upper()
        if not re.fullmatch(r'[A-Z0-9^][A-Z0-9.^_=-]{0,31}', ticker):
            raise ValueError('invalid ticker')
        side = str(side).upper()
        if side not in ('BUY', 'SELL', 'HOLD'):
            raise ValueError('side must be BUY, SELL or HOLD')
        if type(quantity) is not int or quantity < 0 or (side != 'HOLD' and quantity == 0):
            raise ValueError('quantity must be a positive whole number for BUY/SELL')
        if side == 'HOLD' and quantity != 0:
            raise ValueError('HOLD quantity must be zero')
        raw_cents = _cents(price, 'price', positive=True)
        if raw_cents == 0:
            raise ValueError('price must be at least $0.01')
        origin = _utc(source_at)
        current = _utc(now if now is not None else datetime.now(timezone.utc))
        payload = json.dumps([ticker, side, quantity, raw_cents,
                              origin.isoformat(), position_id], separators=(',', ':'))
        digest = hashlib.sha256(payload.encode()).hexdigest()
        sid = _id('signal', event_key)
        order_id = _id('order', event_key)
        fill_id = _id('fill', event_key)
        new_position_id = _id('position', event_key)
        time_str = current.isoformat()
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT payload_hash FROM paper_signals WHERE event_key=?',
                                  (event_key,)).fetchone()
            if previous:
                if previous['payload_hash'] != digest:
                    raise ValueError('event_key reused with different details')
                return self._receipt(db, event_key, duplicate=True)
            age = current - origin
            reason = None
            if age < -timedelta(minutes=1):
                reason = 'future signal timestamp'
            elif age > timedelta(minutes=self.policy.max_signal_age_minutes):
                reason = 'stale signal'
            account = db.execute('SELECT * FROM paper_account WHERE id=1').fetchone()
            positions = db.execute("SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'").fetchone()[0]
            opened = None
            if side == 'BUY':
                if account['halted']:
                    reason = reason or 'risk halt active'
                elif positions:
                    reason = reason or 'only one open position allowed in this policy'
            elif side == 'SELL':
                if not position_id:
                    reason = reason or 'explicit position_id required to close'
                else:
                    opened = db.execute('SELECT * FROM paper_positions WHERE position_id=? AND status=?',
                                        (position_id,'OPEN')).fetchone()
                    if not opened or opened['ticker'] != ticker or opened['quantity'] != quantity:
                        reason = reason or 'open position ID/ticker/quantity mismatch'
            if side == 'HOLD':
                status = 'SKIPPED' if reason is None else 'REJECTED'
            else:
                status = 'FILLED' if reason is None else 'REJECTED'

            slip = Decimal(str(self.policy.slippage_bps)) / 10000
            adverse_price = Decimal(raw_cents) * (1 + slip if side == 'BUY' else 1 - slip)
            fill_cents = int(adverse_price.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            fee_cents = int((Decimal(fill_cents * quantity)
                            * Decimal(str(self.policy.fee_bps)) / 10000)
                           .quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            if status == 'FILLED' and side == 'BUY':
                cost = fill_cents * quantity + fee_cents
                limit = int((Decimal(account['initial_cents'])
                             * Decimal(str(self.policy.max_position_pct)))
                            .quantize(Decimal('1'), rounding=ROUND_HALF_UP))
                if cost > limit:
                    status, reason = 'REJECTED', 'position allocation limit'
                elif cost > account['cash_cents']:
                    status, reason = 'REJECTED', 'insufficient paper cash'

            db.execute('''INSERT INTO paper_signals(
                signal_id,event_key,payload_hash,created_at,source_at,
                ticker,side,quantity,expected_price_cents,position_id,status,reason)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)''',
                (sid,event_key,digest,time_str,origin.isoformat(),ticker,side,
                 quantity,raw_cents,position_id or (new_position_id if side=='BUY'
                                                   and status=='FILLED' else None),status,reason))
            if status == 'FILLED':
                if side == 'BUY':
                    cost = fill_cents * quantity + fee_cents
                    db.execute('''INSERT INTO paper_positions(
                        position_id,ticker,quantity,entry_cents,entry_fee_cents,opened_at,status)
                        VALUES(?,?,?,?,?,?,?)''',
                        (new_position_id,ticker,quantity,fill_cents,fee_cents,time_str,'OPEN'))
                    db.execute('UPDATE paper_account SET cash_cents=cash_cents-? WHERE id=1', (cost,))
                    position_id = new_position_id
                elif side == 'SELL':
                    proceeds = fill_cents * quantity - fee_cents
                    realised = ((fill_cents - opened['entry_cents']) * quantity
                                - fee_cents - opened['entry_fee_cents'])
                    db.execute('''UPDATE paper_positions SET status='CLOSED',exit_cents=?,
                        exit_fee_cents=?,realised_pnl_cents=?,closed_at=?
                        WHERE position_id=? AND status='OPEN' ''',
                        (fill_cents,fee_cents,realised,time_str,position_id))
                    db.execute('UPDATE paper_account SET cash_cents=cash_cents+? WHERE id=1', (proceeds,))
                    total_realised = db.execute('SELECT COALESCE(SUM(realised_pnl_cents),0) '
                                                'FROM paper_positions WHERE status=?', ('CLOSED',)).fetchone()[0]
                    max_loss = (Decimal(account['initial_cents'])
                                * Decimal(str(self.policy.max_realised_loss_pct)))
                    if Decimal(total_realised) <= -max_loss:
                        db.execute("UPDATE paper_account SET halted=1, halt_reason='realised-loss limit' WHERE id=1")
                db.execute('''INSERT INTO paper_orders(
                    order_id,signal_id,side,quantity,status,created_at)
                    VALUES(?,?,?,?,?,?)''', (order_id,sid,side,quantity,'FILLED',time_str))
                db.execute('''INSERT INTO paper_fills(
                    fill_id,order_id,signal_id,position_id,side,quantity,
                    fill_cents,fee_cents,created_at)
                    VALUES(?,?,?,?,?,?,?,?,?)''',
                    (fill_id,order_id,sid,position_id,side,quantity,fill_cents,
                     fee_cents,time_str))
            return self._receipt(db, event_key)

    def halt(self, reason: str):
        """Persist a manual kill switch. No automatic reactivation exists."""
        reason = str(reason).strip()
        if not 1 <= len(reason) <= 240:
            raise ValueError('halt reason must be 1..240 characters')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('UPDATE paper_account SET halted=1, halt_reason=? WHERE id=1',
                       ('operator: ' + reason,))
        return self.status()

    def status(self):
        """Read authoritative stored cash/trades; no invented mark-to-market quotes."""
        with self._connect() as db:
            account = db.execute('SELECT * FROM paper_account WHERE id=1').fetchone()
            open_positions = [dict(row) for row in db.execute('''
                SELECT position_id,ticker,quantity,entry_cents,entry_fee_cents,opened_at
                FROM paper_positions WHERE status='OPEN' ORDER BY opened_at,position_id''')]
            realised = db.execute("SELECT COALESCE(SUM(realised_pnl_cents),0) FROM paper_positions WHERE status='CLOSED'").fetchone()[0]
            return {
                'ok':True, 'mode':'paper', 'cash':_dollars(account['cash_cents']),
                'initial_cash':_dollars(account['initial_cents']),
                'realised_pnl':_dollars(realised),
                'halted':bool(account['halted']), 'halt_reason':account['halt_reason'],
                'open_positions':[{'position_id':p['position_id'], 'ticker':p['ticker'],
                                   'quantity':p['quantity'], 'entry_price':_dollars(p['entry_cents']),
                                   'entry_fee':_dollars(p['entry_fee_cents']),
                                   'opened_at':p['opened_at']} for p in open_positions],
                'signal_count':db.execute('SELECT COUNT(*) FROM paper_signals').fetchone()[0],
                'fill_count':db.execute('SELECT COUNT(*) FROM paper_fills').fetchone()[0],
                'order_count':db.execute('SELECT COUNT(*) FROM paper_orders').fetchone()[0],
                'closed_count':db.execute("SELECT COUNT(*) FROM paper_positions WHERE status='CLOSED'").fetchone()[0],
                'note':'Open positions NOT marked to market; no broker orders exist',
            }
