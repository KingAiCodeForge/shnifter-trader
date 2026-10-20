"""Offline SQLite ledger invariants, including crash/retry and risk denial."""
import concurrent.futures
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from shnifter_paper_ledger import PaperLedger, PaperPolicy

NOW = datetime(2026, 10, 17, 3, 0, tzinfo=timezone.utc)


class TestPaperLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'paper_only.sqlite'
        self.ledger = PaperLedger(self.path)

    def submit(self, key='strategy/AAPL/2026-10-16/BUY', **overrides):
        values = {'event_key':key, 'ticker':'AAPL', 'side':'BUY',
                  'quantity':10,'price':'100',
                  'source_at': NOW-timedelta(minutes=1), 'now':NOW}
        values.update(overrides)
        return self.ledger.submit(**values)

    def test_buy_fill_survives_restart(self):
        receipt = self.submit()
        self.assertEqual(receipt['status'], 'FILLED')
        self.assertEqual(receipt['fill']['quantity'], 10)
        snapshot = PaperLedger(self.path).status()
        self.assertEqual(snapshot['fill_count'], 1)
        self.assertEqual(snapshot['signal_count'], 1)
        self.assertEqual(len(snapshot['open_positions']), 1)
        self.assertEqual(receipt['position_id'], snapshot['open_positions'][0]['position_id'])
        self.assertLess(snapshot['cash'],10000)

    def test_duplicate_event_returns_original_without_new_fill(self):
        original = self.submit()
        retry = PaperLedger(self.path).submit(
            event_key='strategy/AAPL/2026-10-16/BUY', ticker='AAPL',side='BUY',
            quantity=10,price='100',source_at=NOW-timedelta(minutes=1),now=NOW+timedelta(days=5))
        self.assertTrue(retry['duplicate'])
        self.assertFalse(original['duplicate'])
        self.assertEqual(original['fill'],retry['fill'])
        self.assertEqual(self.ledger.status()['fill_count'],1)

    def test_same_key_different_payload_denied(self):
        self.submit()
        with self.assertRaisesRegex(ValueError,'event_key reused'):
            self.submit(quantity=11)
        self.assertEqual(self.ledger.status()['signal_count'],1)

    def test_full_close_by_position_id_and_fee_arithmetic(self):
        trade = self.submit()
        close = self.submit(key='strategy/AAPL/2026-10-17/SELL',side='SELL',
                            quantity=10, price='110',position_id=trade['position_id'])
        self.assertEqual(close['status'],'FILLED')
        snapshot = self.ledger.status()
        self.assertEqual(snapshot['closed_count'],1)
        self.assertEqual(snapshot['open_positions'],[])
        self.assertEqual(snapshot['fill_count'],2)
        self.assertAlmostEqual(snapshot['realised_pnl'],96.90)
        self.assertAlmostEqual(snapshot['cash'],10096.90)

    def test_wrong_id_and_partial_close_cannot_broadcast_to_ticker(self):
        trade = self.submit()
        wrong=self.submit(key='bad-id',side='SELL',position_id='wrong')
        self.assertEqual(wrong['status'],'REJECTED')
        partial=self.submit(key='partial',side='SELL',quantity=2,position_id=trade['position_id'])
        self.assertEqual(partial['status'],'REJECTED')
        self.assertEqual(len(self.ledger.status()['open_positions']),1)
        self.assertEqual(self.ledger.status()['fill_count'],1)

    def test_stale_and_future_signal_rejected(self):
        stale=self.submit(key='stale',source_at=NOW-timedelta(days=1))
        future=self.submit(key='future',source_at=NOW+timedelta(hours=1))
        self.assertEqual(stale['status'],'REJECTED')
        self.assertEqual(stale['reason'],'stale signal')
        self.assertEqual(future['status'],'REJECTED')
        self.assertEqual(future['reason'],'future signal timestamp')
        self.assertEqual(self.ledger.status()['fill_count'],0)

    def test_second_position_and_allocation_cap_enforced(self):
        large=self.submit(key='large',quantity=99)
        self.assertEqual(large['status'],'REJECTED')
        self.assertEqual(large['reason'],'position allocation limit')
        self.submit()
        second=self.submit(key='other-symbol',ticker='MSFT')
        self.assertEqual(second['status'],'REJECTED')
        self.assertIn('one open position',second['reason'])
        self.assertEqual(self.ledger.status()['fill_count'],1)

    def test_losses_halt_new_entries_but_closes_are_still_permitted(self):
        a=self.submit()
        self.submit(key='stopout',side='SELL',price='1',position_id=a['position_id'])
        self.assertTrue(self.ledger.status()['halted'])
        b=self.submit(key='new-entry')
        self.assertEqual(b['status'],'REJECTED')
        self.assertEqual(b['reason'],'risk halt active')

    def test_hold_is_recorded_without_fill(self):
        result=self.submit(key='hold',side='HOLD',quantity=0)
        self.assertEqual(result['status'],'SKIPPED')
        self.assertIsNone(result['fill'])
        self.assertEqual(self.ledger.status()['signal_count'],1)
        self.assertEqual(self.ledger.status()['fill_count'],0)

    def test_risk_policy_cannot_be_changed_on_reopen(self):
        self.submit()
        unsafe = PaperPolicy(max_position_pct=Decimal('.90'))
        with self.assertRaisesRegex(ValueError, 'immutable risk settings'):
            PaperLedger(self.path, policy=unsafe)
        self.assertEqual(self.ledger.status()['fill_count'],1)

    def test_open_existing_reuses_custom_stored_risk_policy(self):
        path=Path(self.tmp.name)/'custom.sqlite'
        original=PaperLedger(path, PaperPolicy(initial_cash=Decimal('1000'),
                                               max_position_pct=Decimal('.10')))
        reopened=PaperLedger.open_existing(path)
        self.assertEqual(reopened.status()['initial_cash'],1000)
        self.assertEqual(reopened.policy.max_position_pct, Decimal('.10'))
        with self.assertRaises(FileNotFoundError):
            PaperLedger.open_existing(Path(self.tmp.name)/'missing.sqlite')

    def test_validation_refuses_invalid_inputs_and_legacy_db(self):
        for kwargs in [{'quantity':0}, {'price':-1}, {'side':'SHORT'},
                       {'source_at':'2026-10-17T03:00:00'}, {'ticker':'../tmp'}]:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.submit(**kwargs)
        with self.assertRaises(ValueError):
            PaperLedger(Path(self.tmp.name)/'shnifter_trading.db')

    def test_concurrent_identical_signal_only_one_fill(self):
        def run(_):
            return self.submit(key='concurrent')
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results=list(pool.map(run,range(6)))
        self.assertEqual([r['duplicate'] for r in results].count(False),1)
        self.assertEqual(self.ledger.status()['fill_count'],1)


if __name__ == '__main__': unittest.main()
