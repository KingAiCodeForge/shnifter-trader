"""End-to-end offline CLI tests for PAPER simulation only."""
import io
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from shnifter_cli import main


class TestPaperCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'paper_only.sqlite'

    def run_cli(self, parts):
        out, err = io.StringIO(), io.StringIO()
        rc = main(['paper', *parts, '--db', str(self.db)],
                  stdout=out, stderr=err)
        return rc, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def test_init_order_duplicate_restart_halt(self):
        rc, result, error = self.run_cli(['init'])
        self.assertEqual(rc, 0, error)
        self.assertEqual(result['initial_cash'], 10000.0)
        self.assertEqual(result['mode'], 'paper')

        source = datetime.now(timezone.utc).isoformat()
        buy = ['order', '--event-key', 'aapl/unique/bar/buy',
               '--ticker', 'AAPL', '--side', 'BUY', '--quantity', '10',
               '--price', '100', '--source-at', source]
        rc, first, error = self.run_cli(buy)
        self.assertEqual(rc, 0, error)
        self.assertEqual(first['status'], 'FILLED')
        rc, second, error = self.run_cli(buy)
        self.assertEqual(rc, 0, error)
        self.assertTrue(second['duplicate'])
        self.assertEqual(second['fill'], first['fill'])
        rc, state, error = self.run_cli(['status'])
        self.assertEqual(state['fill_count'], 1)
        self.assertEqual(state['order_count'], 1)
        self.assertEqual(state['signal_count'], 1)

        rc, state, error = self.run_cli(['halt','--reason','manual test'])
        self.assertEqual(rc, 0, error)
        self.assertTrue(state['halted'])
        self.assertEqual(state['halt_reason'], 'operator: manual test')

        rc, denied, error = self.run_cli(
            ['order', '--event-key','new', '--ticker','MSFT','--side','BUY',
             '--quantity','1','--price','10','--source-at',source]
        )
        self.assertEqual(rc, 1)
        self.assertEqual(denied['status'], 'REJECTED')
        self.assertEqual(denied['reason'], 'risk halt active')

        rc, close, error = self.run_cli(
            ['order', '--event-key','close', '--ticker','AAPL','--side','SELL',
             '--quantity','10','--price','105','--source-at',source,
             '--position-id',first['position_id']]
        )
        self.assertEqual(rc, 0, error)
        self.assertEqual(close['status'], 'FILLED')
        rc, state, error = self.run_cli(['status'])
        self.assertEqual(state['closed_count'], 1)
        self.assertEqual(state['fill_count'], 2)
        self.assertFalse(state['open_positions'])

    def test_no_reinitialization_or_implicit_creation(self):
        rc, doc, error = self.run_cli(['status'])
        self.assertEqual(rc, 1)
        self.assertIsNone(doc)
        self.assertIn('not initialized', error)
        self.assertFalse(self.db.exists())
        self.run_cli(['init'])
        rc, doc, error = self.run_cli(['init'])
        self.assertEqual(rc, 1)
        self.assertIn('already exists', error)

    def test_risk_config_persists_after_restart(self):
        rc, doc, error = self.run_cli(
            ['init','--initial-cash','1000',
             '--max-position-pct','0.10','--max-realised-loss-pct','0.02']
        )
        self.assertEqual(rc, 0,error)
        rc, doc, error = self.run_cli(['status'])
        self.assertEqual(doc['initial_cash'], 1000.0)
        rc, order, error = self.run_cli(
            ['order','--event-key','too_large','--ticker','AAPL',
             '--side','BUY','--quantity','2','--price','100',
             '--source-at',datetime.now(timezone.utc).isoformat()]
        )
        self.assertEqual(rc, 1)
        self.assertEqual(order['reason'], 'position allocation limit')

    def test_no_real_broker_capability(self):
        from shnifter_cli import build_parser
        parser = build_parser()
        with self.assertRaises(SystemExit) as error:
            parser.parse_args(['paper', 'live', '--db', str(self.db)])
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
