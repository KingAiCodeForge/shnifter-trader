"""Regression of admission guards, event-capacity safety and replay purity.

All orders/fills are local simulation inputs, not broker interactions.
"""
from __future__ import annotations

import copy
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import shnifter_order_events as events
from shnifter_order_events import PaperEventStore, IntegrityError, digest, canonical


class BoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'account.sqlite'
        self.store = PaperEventStore.create(self.db)

    def submit(self, oid='b1', side='BUY', qty=2):
        return self.store.append('intent-'+oid, 'SUBMIT', dict(
            order_id=oid, ticker='AAPL', side=side, quantity=qty,
            limit_cents=10000, fee_budget_cents=100))

    def emit(self, kind, oid='b1', event_id=None, **extra):
        return self.store.append(event_id or kind+'-'+oid, kind, dict(order_id=oid, **extra))

    def fill(self, oid='b1', qty=2, eid='f1'):
        return self.emit('FILL', oid, event_id='fill-'+eid, execution_id=eid,
                         quantity=qty, price_cents=10000, fee_cents=10)

    def freeze(self, mode):
        if mode == 'halt':
            return self.store.append('halt', 'HALT', {'reason':'operator requested'})
        self.emit('TRANSMIT')
        if mode == 'unknown':
            return self.emit('UNKNOWN', reason='missing response')
        if mode == 'quarantine':
            return self.fill(qty=99, eid='bad')
        if mode == 'cancelled':
            self.emit('CANCEL_REQUEST')
            return self.emit('CANCEL_ACK')
        if mode == 'rejected':
            return self.emit('REJECT', reason='simulated broker rejection')
        raise AssertionError(mode)

    def test_staged_buy_cannot_transmit_after_manual_halt(self):
        self.submit()
        self.freeze('halt')
        before = self.store.status()
        with self.assertRaisesRegex(ValueError, 'halt'):
            self.emit('TRANSMIT')
        self.assertEqual(before, self.store.status())

    def test_staged_orders_cannot_bypass_account_reconciliation(self):
        for mode in ('unknown', 'quarantine', 'cancelled', 'rejected'):
            with self.subTest(mode=mode):
                path = Path(self.temp.name) / (mode+'.sqlite')
                self.store = PaperEventStore.create(path)
                self.submit(); self.submit('staged')
                self.freeze(mode)
                before = self.store.status()
                with self.assertRaisesRegex(ValueError, 'reconciliation'):
                    self.emit('TRANSMIT', 'staged')
                self.assertEqual(before, self.store.status())

    def test_unreconciled_terminal_orders_block_new_intents(self):
        for mode in ('cancelled', 'rejected'):
            with self.subTest(mode=mode):
                self.store = PaperEventStore.create(Path(self.temp.name)/(mode+'.sqlite'))
                self.submit(); self.freeze(mode)
                with self.assertRaisesRegex(ValueError, 'reconciliation'):
                    self.submit('new')

    def test_reconciliation_resolves_guard_but_manual_halt_does_not_reset(self):
        self.submit(); self.submit('staged'); self.freeze('cancelled')
        self.emit('RECONCILE', status='CANCELLED', filled_quantity=0, execution_ids=[])
        self.store.append('halt', 'HALT', {'reason':'still halted'})
        with self.assertRaisesRegex(ValueError, 'halt'):
            self.emit('TRANSMIT', 'staged')

    def test_verified_active_reconciliation_permits_staged_transmission(self):
        self.submit(); self.submit('staged'); self.freeze('unknown')
        self.emit('RECONCILE', status='ACTIVE', filled_quantity=0, execution_ids=[])
        result = self.emit('TRANSMIT', 'staged')
        self.assertEqual(result['orders']['staged']['status'], 'PENDING_SUBMIT')

    def test_local_cancel_of_frozen_staged_order_releases_reserved_cash(self):
        self.submit(); self.freeze('halt')
        result = self.emit('CANCEL_REQUEST')
        self.assertEqual(result['orders']['b1']['status'], 'CANCELLED')
        self.assertEqual(result['reserved_cash_cents'], 0)
        self.assertTrue(result['manual_halt'])

    def test_already_sent_fill_is_accounted_after_manual_halt(self):
        self.submit(); self.emit('TRANSMIT'); self.freeze('halt')
        result = self.fill()
        self.assertEqual(result['orders']['b1']['status'], 'FILLED')
        self.assertEqual(result['positions']['AAPL']['quantity'], 2)
        self.assertTrue(result['manual_halt'])

    def test_close_only_sell_can_transmit_during_manual_halt(self):
        self.submit(); self.emit('TRANSMIT'); self.fill()
        self.submit('sell', side='SELL')
        self.freeze('halt')
        result = self.emit('TRANSMIT', 'sell')
        self.assertEqual(result['orders']['sell']['status'], 'PENDING_SUBMIT')
        self.assertTrue(result['manual_halt'])

    def test_no_sell_transmission_when_account_state_is_unknown(self):
        self.submit(); self.emit('TRANSMIT'); self.fill()
        self.submit('sell', side='SELL'); self.submit('pending')
        self.emit('TRANSMIT', 'pending')
        self.emit('UNKNOWN', 'pending', reason='uncertain unrelated order')
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            self.emit('TRANSMIT', 'sell')

    def test_halt_cannot_retroactively_unsend_or_unbook(self):
        self.submit(); sent = self.emit('TRANSMIT')
        state = self.freeze('halt')
        duplicate = self.emit('TRANSMIT')
        self.assertTrue(state['orders']['b1']['transmitted'])
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(duplicate['event_count'], state['event_count'])
        self.assertEqual(sent['reserved_cash_cents'], state['reserved_cash_cents'])

    def test_restart_preserves_transmit_guard(self):
        self.submit(); self.freeze('halt')
        self.store = PaperEventStore(self.db)
        with self.assertRaisesRegex(ValueError, 'halt'):
            self.emit('TRANSMIT')

    def test_quarantined_account_still_accepts_known_order_fills(self):
        self.submit(); self.emit('TRANSMIT'); self.fill(qty=99, eid='bad')
        result = self.fill(eid='good')
        self.assertFalse(result['ok'])
        self.assertEqual(result['positions']['AAPL']['quantity'], 2)
        self.assertEqual(result['orders']['b1']['status'], 'FILLED')

    def test_capacity_limits_new_entries_not_halt_or_known_fill(self):
        with patch.object(events, 'MAX_EVENTS', 3):
            self.submit(); self.emit('TRANSMIT')
            self.store.append('stop-at-limit', 'HALT', {'reason':'capacity reached'})
            result = self.fill()
            self.assertEqual(result['event_count'], 5)
            self.assertEqual(result['orders']['b1']['status'], 'FILLED')
            self.assertTrue(PaperEventStore(self.db).status()['manual_halt'])

    def test_capacity_keeps_cancel_and_reconciliation_available(self):
        with patch.object(events, 'MAX_EVENTS', 3):
            self.submit(); self.emit('TRANSMIT')
            self.emit('CANCEL_REQUEST'); self.emit('CANCEL_ACK')
            self.emit('RECONCILE', status='CANCELLED', filled_quantity=0, execution_ids=[])
            result = self.store.status()
            self.assertEqual(result['reserved_cash_cents'], 0)
            self.assertEqual(result['event_count'], 6)

    def test_capacity_blocks_new_buy_intents(self):
        with patch.object(events, 'MAX_EVENTS', 2):
            self.submit()
            with self.assertRaisesRegex(ValueError, 'capacity'):
                self.submit('new')

    def test_capacity_blocks_staged_buy_transmission(self):
        with patch.object(events, 'MAX_EVENTS', 2):
            self.submit()
            with self.assertRaisesRegex(ValueError, 'capacity'):
                self.emit('TRANSMIT')

    def test_capacity_does_not_prevent_risk_reducing_sell(self):
        self.submit(); self.emit('TRANSMIT'); self.fill()
        with patch.object(events, 'MAX_EVENTS', 4):
            self.submit('sell', side='SELL')
            self.emit('TRANSMIT', 'sell')
            result = self.fill('sell', eid='sold')
            self.assertEqual(result['positions']['AAPL']['quantity'], 0)
            self.assertTrue(result['ok'])

    def test_capacity_duplicate_delivery_still_idempotent(self):
        self.submit(); self.emit('TRANSMIT'); first = self.fill()
        with patch.object(events, 'MAX_EVENTS', 4):
            result = self.fill()
            self.assertTrue(result['duplicate'])
            self.assertEqual(first['state_sha256'], result['state_sha256'])

    def test_capacity_is_visible_as_entry_admission_reason(self):
        with patch.object(events, 'MAX_EVENTS', 2):
            self.submit()
            result = self.store.status()
            self.assertIn('event_admission_limit', result['entry_block_reasons'])
            self.assertFalse(result['new_entries_allowed'])
            self.assertFalse(result['live_authorized'])

    def test_manual_and_uncertain_blocks_visible_in_status(self):
        self.submit(); self.emit('TRANSMIT')
        self.emit('UNKNOWN', reason='lost response')
        self.store.append('halt', 'HALT', {'reason':'operator'})
        result = self.store.status()
        self.assertCountEqual(result['entry_block_reasons'], ['manual_halt', 'unreconciled_state'])
        self.assertFalse(result['new_entries_allowed'])

    def test_replay_does_not_deepcopy_entire_account_per_event(self):
        for i in range(12):
            oid = 'order'+str(i)
            self.submit(oid); self.emit('CANCEL_REQUEST', oid)
        real_copy = copy.deepcopy
        def reject_account_copy(obj, *args, **kw):
            if type(obj) is dict and 'positions' in obj and 'orders' in obj:
                raise AssertionError('full account was copied during replay')
            return real_copy(obj, *args, **kw)
        with patch.object(events.copy, 'deepcopy', side_effect=reject_account_copy):
            self.assertTrue(self.store.status()['ok'])

    def test_public_reducer_keeps_input_and_result_independent(self):
        state = self.submit()
        before = copy.deepcopy(state)
        result = events.reduce_event(state, 'ack-local', 'TRANSMIT', {'order_id':'b1'})
        result['orders']['b1']['execution_ids'].append('caller-mutated')
        self.assertEqual(state, before)

    def test_v1_database_cannot_be_silently_reinterpreted(self):
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE metadata SET version='shnifter.paper-events.v1'")
        original = self.db.read_bytes()
        with self.assertRaisesRegex(IntegrityError, 'version'):
            self.store.status()
        self.assertEqual(original, self.db.read_bytes())

    def test_malformed_saved_envelope_is_controlled_integrity_failure(self):
        # Recompute the hash intentionally: schema validation must work independently
        # of content hashes. This is a corrupted local fixture, not external evidence.
        with sqlite3.connect(self.db) as db:
            db.execute('DROP TRIGGER events_no_update')
            seq, eid, at, _, prev, _ = db.execute('SELECT * FROM events').fetchone()
            text = 'null'
            db.execute('UPDATE events SET payload_json=?,event_hash=?',
                       (text,digest([seq,eid,at,text,prev])))
        with self.assertRaisesRegex(IntegrityError, 'envelope'):
            self.store.status()

    def test_halt_and_transmit_race_is_serialised_by_database(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        for i in range(10):
            path = Path(self.temp.name) / ('race'+str(i)+'.sqlite')
            self.store = PaperEventStore.create(path)
            self.submit()
            barrier = Barrier(2)
            def halt():
                barrier.wait(timeout=5)
                return PaperEventStore(path).append('stop', 'HALT', {'reason':'race'})
            def transmit():
                barrier.wait(timeout=5)
                try:
                    return PaperEventStore(path).append('send', 'TRANSMIT', {'order_id':'b1'})
                except ValueError:
                    return None
            with ThreadPoolExecutor(max_workers=2) as pool:
                h = pool.submit(halt); t = pool.submit(transmit)
                h.result(timeout=10); sent = t.result(timeout=10)
            with sqlite3.connect(path) as db:
                sequences = dict(db.execute('SELECT event_id,seq FROM events'))
            state = PaperEventStore(path).status()
            self.assertTrue(state['manual_halt'])
            if sent is not None:
                self.assertLess(sequences['send'], sequences['stop'])
            else:
                self.assertNotIn('send', sequences)
                self.assertEqual(state['orders']['b1']['status'], 'NEW')

    def test_corrupted_envelope_cli_returns_structured_error_not_traceback(self):
        import io
        from shnifter_cli import main
        with sqlite3.connect(self.db) as db:
            db.execute('DROP TRIGGER events_no_update')
            seq, eid, at, _, prev, _ = db.execute('SELECT * FROM events').fetchone()
            text = 'null'
            db.execute('UPDATE events SET payload_json=?,event_hash=?',
                       (text,digest([seq,eid,at,text,prev])))
        out, err = io.StringIO(), io.StringIO()
        rc = main(['paper-events','status','--db',str(self.db)], stdout=out, stderr=err)
        self.assertEqual(rc, 1)
        self.assertEqual(out.getvalue(), '')
        result = json.loads(err.getvalue())
        self.assertFalse(result['ok'])
        self.assertFalse(result['live_authorized'])
        self.assertIn('envelope', result['error'])

    def test_forged_invalid_lifecycle_is_rejected_during_replay(self):
        self.submit(); self.freeze('halt')
        with closing(self.store._connect(write=True)) as db:
            db.execute('BEGIN IMMEDIATE')
            _, n, prev = self.store._load(db)
            self.store._insert(db,n+1,'forged-send',{'kind':'TRANSMIT','data':{'order_id':'b1'}},prev)
            db.execute('COMMIT')
        with self.assertRaisesRegex(IntegrityError, 'halt'):
            self.store.status()

if __name__ == '__main__':
    unittest.main()
