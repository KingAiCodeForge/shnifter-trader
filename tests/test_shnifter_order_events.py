"""Offline paper lifecycle, concurrency and crash tests; no quotes/broker calls."""
import copy
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from shnifter_order_events import PaperEventStore, IntegrityError, cents, reduce_event


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'events.sqlite'
        self.store = PaperEventStore.create(self.db)

    def submit(self, oid='b1', side='BUY', qty=5, price=10000, fee=100):
        return self.store.append('intent-' + oid, 'SUBMIT', dict(
            order_id=oid, ticker='AAPL', side=side, quantity=qty,
            limit_cents=price, fee_budget_cents=fee))

    def emit(self, kind, oid='b1', event_id=None, **kw):
        return self.store.append(event_id or kind + '-' + oid, kind, dict(order_id=oid, **kw))

    def fill(self, eid='f1', oid='b1', qty=2, price=9900, fee=30, event_id=None):
        return self.emit('FILL', oid, event_id=event_id or 'fill-' + eid,
                         execution_id=eid, quantity=qty, price_cents=price, fee_cents=fee)

    def started(self):
        self.submit()
        return self.emit('TRANSMIT')

    def buy_all(self):
        self.started()
        return self.fill(qty=5)

    def reconcile(self, status='CANCELLED', qty=2, ids=None, oid='b1'):
        return self.emit('RECONCILE', oid, status=status, filled_quantity=qty,
                         execution_ids=['f1'] if ids is None else ids)

    def test_submit_reserves_cash_but_never_fills(self):
        result = self.submit()
        self.assertEqual(result['cash_cents'], 1000000)
        self.assertEqual(result['available_cash_cents'], 949900)
        self.assertEqual(result['reserved_cash_cents'], 50100)
        self.assertEqual(result['orders']['b1']['status'], 'NEW')
        self.assertFalse(result['live_authorized'])
        self.assertEqual(result['executions'], {})

    def test_partial_fill_changes_only_actual_quantity_and_cash(self):
        self.started()
        state = self.fill()
        self.assertEqual(state['orders']['b1']['status'], 'PARTIAL')
        self.assertEqual(state['cash_cents'], 980170)
        self.assertEqual(state['positions']['AAPL'], {'quantity': 2, 'cost_cents': 19830})
        self.assertEqual(state['reserved_cash_cents'], 30070)

    def test_full_fill_releases_unused_fee_and_price_reservations(self):
        self.started()
        self.fill()
        result = self.fill('f2', qty=3, price=9950, fee=20)
        self.assertEqual(result['orders']['b1']['status'], 'FILLED')
        self.assertEqual(result['reserved_cash_cents'], 0)
        self.assertEqual(result['cash_cents'], 950300)
        self.assertEqual(result['positions']['AAPL']['cost_cents'], 49700)

    def test_same_event_retry_is_idempotent_across_restart(self):
        self.started()
        a = self.fill()
        self.store = PaperEventStore(self.db)
        b = self.fill()
        self.assertTrue(b['duplicate'])
        self.assertEqual(a['state_sha256'], b['state_sha256'])
        self.assertEqual(a['event_count'], b['event_count'])
        self.assertEqual(a['head_hash'], b['head_hash'])

    def test_same_execution_in_new_delivery_is_not_booked_twice(self):
        self.started()
        a = self.fill()
        b = self.fill(event_id='new-delivery')
        self.assertEqual(a['state_sha256'], b['state_sha256'])
        self.assertEqual(a['cash_cents'], b['cash_cents'])
        self.assertEqual(b['event_count'], a['event_count'] + 1)

    def test_conflicting_event_id_is_rejected_without_write(self):
        self.started()
        before = self.fill()
        with self.assertRaises(IntegrityError):
            self.fill(price=9800)
        self.assertEqual(self.store.status()['head_hash'], before['head_hash'])

    def test_conflicting_execution_id_is_preserved_in_quarantine(self):
        self.started()
        a = self.fill()
        b = self.fill(event_id='conflicting-delivery', price=9800)
        self.assertFalse(b['ok'])
        self.assertEqual(a['cash_cents'], b['cash_cents'])
        self.assertIn('execution_id reused', b['quarantine'][0]['reason'])
        with self.assertRaisesRegex(ValueError, 'reconciliation'):
            self.submit('b2')
        self.assertFalse(PaperEventStore(self.db).verify()['ok'])

    def test_fill_can_precede_ack_and_late_ack_does_not_regress(self):
        self.started()
        self.fill()
        result = self.emit('ACK')
        self.assertEqual(result['orders']['b1']['status'], 'PARTIAL')
        self.fill('f2', qty=3)
        result = self.emit('ACK', event_id='later-ack')
        self.assertEqual(result['orders']['b1']['status'], 'FILLED')

    def test_ack_never_clears_unknown(self):
        self.started()
        self.emit('UNKNOWN', reason='timeout after simulated transmit')
        state = self.emit('ACK')
        self.assertEqual(state['orders']['b1']['status'], 'UNKNOWN')

    def test_unknown_retains_cash_and_forbids_transmit_retry(self):
        self.started()
        result = self.emit('UNKNOWN', reason='no acknowledgement')
        self.assertEqual(result['reserved_cash_cents'], 50100)
        with self.assertRaises(ValueError):
            self.emit('TRANSMIT', event_id='unsafe-retry')
        with self.assertRaises(ValueError):
            self.submit('b2')
        state = self.reconcile('ACTIVE', 0, [])
        self.assertEqual(state['orders']['b1']['status'], 'ACKNOWLEDGED')
        self.submit('b2')

    def test_cancel_does_not_clear_prior_transmission_uncertainty(self):
        self.started()
        self.emit('UNKNOWN', reason='timeout')
        self.emit('CANCEL_REQUEST')
        state = self.emit('CANCEL_ACK')
        self.assertTrue(state['orders']['b1']['uncertain'])
        self.assertTrue(state['requires_reconciliation'])
        with self.assertRaises(ValueError):
            self.submit('b2')
        state = self.reconcile(qty=0, ids=[])
        self.assertFalse(state['requires_reconciliation'])
        self.submit('b2')

    def test_late_cancel_ack_does_not_change_reconciled_terminal_state(self):
        self.started()
        self.emit('CANCEL_REQUEST')
        self.reconcile('REJECTED', 0, [])
        state = self.emit('CANCEL_ACK')
        self.assertEqual(state['orders']['b1']['status'], 'REJECTED')
        self.assertEqual(state['reserved_cash_cents'], 0)

    def test_cancel_request_preserves_cash_and_late_fill(self):
        self.started()
        state = self.emit('CANCEL_REQUEST')
        self.assertEqual(state['orders']['b1']['status'], 'CANCEL_PENDING')
        self.assertEqual(state['reserved_cash_cents'], 50100)
        state = self.fill()
        self.assertEqual(state['orders']['b1']['status'], 'CANCEL_PENDING')
        self.assertEqual(state['positions']['AAPL']['quantity'], 2)

    def test_cancel_ack_alone_does_not_release_reserve(self):
        self.started()
        self.emit('CANCEL_REQUEST')
        a = self.emit('CANCEL_ACK')
        self.assertEqual(a['orders']['b1']['status'], 'CANCELLED')
        self.assertFalse(a['orders']['b1']['settled'])
        self.assertEqual(a['reserved_cash_cents'], 50100)
        b = self.fill()
        self.assertEqual(b['orders']['b1']['status'], 'CANCELLED')
        self.assertEqual(b['reserved_cash_cents'], 30070)
        c = self.reconcile()
        self.assertTrue(c['orders']['b1']['settled'])
        self.assertEqual(c['reserved_cash_cents'], 0)

    def test_cancel_ack_after_full_fill_preserves_filled(self):
        self.started()
        self.emit('CANCEL_REQUEST')
        self.fill(qty=5)
        state = self.emit('CANCEL_ACK')
        self.assertEqual(state['orders']['b1']['status'], 'FILLED')

    def test_untransmitted_cancel_is_local_and_releases_cash(self):
        self.submit()
        result = self.emit('CANCEL_REQUEST')
        self.assertTrue(result['orders']['b1']['settled'])
        self.assertEqual(result['available_cash_cents'], 1000000)

    def test_late_new_fill_after_reconciled_cancel_halts_in_quarantine(self):
        self.started()
        self.emit('CANCEL_REQUEST')
        self.emit('CANCEL_ACK')
        before = self.reconcile(qty=0, ids=[])
        after = self.fill()
        self.assertFalse(after['ok'])
        self.assertEqual(before['cash_cents'], after['cash_cents'])
        self.assertEqual(len(after['quarantine']), 1)

    def test_duplicate_old_fill_after_reconcile_is_not_a_new_fill(self):
        self.started()
        self.fill()
        self.emit('CANCEL_REQUEST')
        self.emit('CANCEL_ACK')
        before = self.reconcile()
        after = self.fill(event_id='delayed-duplicate')
        self.assertTrue(after['ok'])
        self.assertEqual(before['state_sha256'], after['state_sha256'])

    def test_missing_execution_reconciliation_is_not_silently_balanced(self):
        self.started()
        self.fill()
        state = self.reconcile('ACTIVE', 3, ['f1', 'unreceived'])
        self.assertFalse(state['ok'])
        self.assertEqual(state['positions']['AAPL']['quantity'], 2)
        self.assertEqual(state['reserved_cash_cents'], 30070)

    def test_oversized_fill_is_quarantined(self):
        self.started()
        state = self.fill(qty=6)
        self.assertFalse(state['ok'])
        self.assertEqual(state['cash_cents'], 1000000)
        self.assertEqual(state['executions'], {})

    def test_limit_violation_is_quarantined(self):
        self.started()
        state = self.fill(price=10001)
        self.assertFalse(state['ok'])
        self.assertIn('limit price', state['quarantine'][0]['reason'])

    def test_fee_overrun_is_quarantined(self):
        self.started()
        state = self.fill(fee=101)
        self.assertFalse(state['ok'])
        self.assertIn('fee budget', state['quarantine'][0]['reason'])

    def test_multiple_sells_cannot_reserve_same_shares(self):
        self.buy_all()
        self.submit('s1', 'SELL', 4, price=10000)
        with self.assertRaises(ValueError):
            self.submit('s2', 'SELL', 2, price=10000)

    def test_short_sale_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'unreserved long'):
            self.submit('s1', 'SELL')

    def test_average_cost_partial_sales_reconcile_exactly(self):
        self.buy_all()  # Cost 49530 for 5 shares.
        self.submit('s1', 'SELL', 5, price=10000, fee=100)
        self.emit('TRANSMIT', 's1')
        a = self.fill('sell1', 's1', 2, price=11000, fee=20)
        self.assertEqual(a['positions']['AAPL'], {'quantity': 3, 'cost_cents': 29718})
        b = self.fill('sell2', 's1', 3, price=11100, fee=30)
        self.assertEqual(b['positions']['AAPL'], {'quantity': 0, 'cost_cents': 0})
        self.assertEqual(b['realised_pnl_cents'], 5720)
        self.assertEqual(b['cash_cents'], 1005720)

    def test_manual_halt_survives_restart_but_permits_closing_sale(self):
        self.buy_all()
        self.store.append('stop', 'HALT', {'reason': 'operator test'})
        self.store = PaperEventStore(self.db)
        with self.assertRaisesRegex(ValueError, 'manual halt'):
            self.submit('b2')
        state = self.submit('s1', 'SELL', 5)
        self.assertTrue(state['manual_halt'])
        self.assertEqual(state['reserved_shares']['AAPL'], 5)

    def test_rejected_sent_order_reserves_until_reconciled(self):
        self.started()
        state = self.emit('REJECT', reason='simulated rejection')
        self.assertEqual(state['reserved_cash_cents'], 50100)
        state = self.reconcile('REJECTED', 0, [])
        self.assertEqual(state['reserved_cash_cents'], 0)

    def test_malformed_input_does_not_append(self):
        before = self.store.status()
        for bad in (0, -1, True, 1.5):
            with self.subTest(quantity=bad), self.assertRaises(ValueError):
                self.submit(qty=bad)
        self.assertEqual(before['head_hash'], self.store.status()['head_hash'])

    def test_money_is_exact_cents_not_silently_rounded(self):
        for bad in (None, True, 'NaN', 'Infinity', '-1', '.001'):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                cents(bad, 'cash')
        self.assertEqual(cents('100.01', 'cash'), 10001)

    def test_pure_reducer_does_not_change_original_snapshot(self):
        state = self.store.status()
        before = copy.deepcopy(state)
        after = reduce_event(state, 'halt-copy', 'HALT', {'reason': 'test'})
        self.assertEqual(state, before)
        self.assertTrue(after['manual_halt'])
        self.assertFalse(state['manual_halt'])

    def test_reading_does_not_create_or_reset_db(self):
        missing = self.db.with_name('missing.sqlite')
        with self.assertRaises(FileNotFoundError):
            PaperEventStore(missing)
        self.assertFalse(missing.exists())
        with self.assertRaises(FileExistsError):
            PaperEventStore.create(self.db)

    def test_other_database_is_rejected_without_mutation(self):
        foreign = self.db.with_name('foreign.sqlite')
        with sqlite3.connect(foreign) as db:
            db.execute('CREATE TABLE originals(x)')
        before = foreign.read_bytes()
        with self.assertRaises(IntegrityError):
            PaperEventStore(foreign).status()
        self.assertEqual(before, foreign.read_bytes())

    def test_hash_tampering_is_detected(self):
        self.started()
        with sqlite3.connect(self.db) as db:
            db.execute('DROP TRIGGER events_no_update')
            db.execute("UPDATE events SET recorded_at='changed' WHERE seq=2")
        with self.assertRaises(IntegrityError):
            self.store.verify()
        with self.assertRaises(IntegrityError):
            self.submit('new')

    def test_normal_sql_mutation_is_blocked(self):
        with sqlite3.connect(self.db) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM events')
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE events SET event_id='changed'")

    def test_database_failure_after_insert_rolls_back_everything(self):
        self.started()
        before = self.store.status()
        original = PaperEventStore._insert
        def failing(*args, **kwargs):
            original(*args, **kwargs)
            raise sqlite3.OperationalError('injected disk failure before commit')
        with patch.object(PaperEventStore, '_insert', side_effect=failing):
            with self.assertRaises(sqlite3.OperationalError):
                self.fill()
        self.assertEqual(before, self.store.status())

    def test_concurrent_repeated_event_commits_exactly_once(self):
        self.started()
        def repeat(_):
            store = PaperEventStore(self.db)
            return store.append('same', 'FILL', dict(order_id='b1', execution_id='f1',
                quantity=2, price_cents=9900, fee_cents=30))
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(repeat, range(12)))
        self.assertEqual(sum(not r['duplicate'] for r in results), 1)
        state = self.store.status()
        self.assertEqual(state['event_count'], 4)
        self.assertEqual(state['positions']['AAPL']['quantity'], 2)

    def test_concurrent_orders_cannot_oversubscribe_reserved_cash(self):
        path = self.db.with_name('small.sqlite')
        PaperEventStore.create(path, initial_cash=200, max_order_value=150, max_total_value=200)
        def submit(i):
            try:
                return PaperEventStore(path).append('event'+str(i), 'SUBMIT', dict(
                    order_id='o'+str(i), ticker='AAPL', side='BUY', quantity=1,
                    limit_cents=15000, fee_budget_cents=0))
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, [1, 2]))
        self.assertEqual(sum(r is not None for r in results), 1)
        self.assertEqual(PaperEventStore(path).status()['reserved_cash_cents'], 15000)

    def test_process_death_mid_transaction_loses_no_committed_event(self):
        self.started()
        before = self.store.status()
        program = '''import os,sys
from contextlib import closing
from shnifter_order_events import PaperEventStore
s=PaperEventStore(sys.argv[1])
with closing(s._connect(write=True)) as db:
 db.execute('BEGIN IMMEDIATE')
 state,n,prev=s._load(db)
 s._insert(db,n+1,'crash-event',{'kind':'HALT','data':{'reason':'uncommitted'}},prev)
 os._exit(71)
'''
        proc = subprocess.run([sys.executable, '-c', program, str(self.db)],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 71, proc.stderr)
        self.assertEqual(before, PaperEventStore(self.db).status())

    def test_new_process_reconstructs_identical_cash_and_positions(self):
        self.started()
        self.fill()
        expected = self.store.status()
        run = subprocess.run([sys.executable, '-c',
            'import sys,json;from shnifter_order_events import PaperEventStore;print(json.dumps(PaperEventStore(sys.argv[1]).status()))',
            str(self.db)], capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(expected, json.loads(run.stdout))


if __name__ == '__main__':
    unittest.main()
