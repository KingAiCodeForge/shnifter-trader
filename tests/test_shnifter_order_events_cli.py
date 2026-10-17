"""Local CLI end-to-end tests. Every execution is an explicit simulated event."""
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from shnifter_cli import main


class EventCLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'events.sqlite'

    def command(self, *args):
        out, err = io.StringIO(), io.StringIO()
        rc = main(['paper-events', *args, '--db', str(self.db)], stdout=out, stderr=err)
        return rc, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def submit(self):
        return self.command('submit', '--event-id', 'intent1', '--order-id', 'o1',
            '--ticker', 'aapl', '--side', 'BUY', '--quantity', '5', '--limit-price', '100', '--fee-budget', '1')

    def test_partial_cancel_reconcile_end_to_end(self):
        self.assertEqual(self.command('init')[0], 0)
        rc, result, err = self.submit()
        self.assertEqual(rc, 0, err)
        self.assertFalse(result['live_authorized'])
        self.assertEqual(result['orders']['o1']['status'], 'NEW')
        self.assertEqual(self.command('transmit', '--event-id', 'send1', '--order-id', 'o1')[0], 0)
        self.assertEqual(self.command('ack', '--event-id', 'ack1', '--order-id', 'o1')[0], 0)
        rc, result, err = self.command('fill', '--event-id', 'fill1', '--order-id', 'o1',
            '--execution-id', 'exec1', '--quantity', '2', '--price', '99.00', '--fee', '.30')
        self.assertEqual(rc, 0, err)
        self.assertEqual(result['orders']['o1']['status'], 'PARTIAL')
        self.assertEqual(self.command('cancel-request', '--event-id', 'cancel1', '--order-id', 'o1')[0], 0)
        rc, result, err = self.command('cancel-ack', '--event-id', 'cancelled1', '--order-id', 'o1')
        self.assertEqual(result['reserved_cash_cents'], 30070)
        rc, result, err = self.command('reconcile', '--event-id', 'recon1', '--order-id', 'o1',
            '--status', 'CANCELLED', '--filled-quantity', '2', '--execution-ids', 'exec1')
        self.assertEqual(rc, 0, err)
        self.assertEqual(result['reserved_cash_cents'], 0)
        self.assertEqual(result['positions']['AAPL']['quantity'], 2)
        self.assertEqual(self.command('verify')[0], 0)

    def test_missing_database_does_not_create_one(self):
        rc, result, err = self.command('status')
        self.assertEqual(rc, 1)
        self.assertFalse(self.db.exists())
        self.assertFalse(json.loads(err)['live_authorized'])

    def test_refuses_reinitialisation(self):
        self.command('init')
        self.submit()
        before = self.command('status')[1]
        self.assertEqual(self.command('init')[0], 1)
        self.assertEqual(self.command('status')[1], before)

    def test_retry_submit_uses_stable_event_identity(self):
        self.command('init')
        first = self.submit()[1]
        second = self.submit()[1]
        self.assertEqual(first['head_hash'], second['head_hash'])
        self.assertTrue(second['duplicate'])

    def test_quarantine_uses_exit_three_and_persists_evidence(self):
        self.command('init')
        self.submit()
        self.command('transmit', '--event-id', 'send1', '--order-id', 'o1')
        rc, result, err = self.command('fill', '--event-id', 'badfill', '--order-id', 'o1',
            '--execution-id', 'badexec', '--quantity', '50', '--price', '99', '--fee', '.30')
        self.assertEqual(rc, 3, err)
        self.assertFalse(result['ok'])
        self.assertFalse(result['live_authorized'])
        rc, state, err = self.command('verify')
        self.assertEqual(rc, 3)
        self.assertEqual(state['quarantine'][0]['event_id'], 'badfill')

    def test_halt_persists_and_blocks_new_entry(self):
        self.command('init')
        rc, result, err = self.command('halt', '--event-id', 'stop1', '--reason', 'operator halt')
        self.assertTrue(result['manual_halt'])
        self.assertEqual(self.submit()[0], 1)

    def test_invalid_fractional_cents_do_not_make_an_order(self):
        self.command('init')
        rc, result, err = self.command('submit', '--event-id', 'intent1', '--order-id', 'o1',
            '--ticker', 'AAPL', '--side', 'BUY', '--quantity', '1', '--limit-price', '100.001', '--fee-budget', '1')
        self.assertEqual(rc, 1)
        self.assertEqual(self.command('status')[1]['orders'], {})

    def test_new_process_status_matches_in_process(self):
        self.command('init')
        self.submit()
        entry = Path(__file__).resolve().parents[1] / 'shnifter_cli.py'
        proc = subprocess.run([sys.executable, str(entry), 'paper-events', 'status', '--db', str(self.db)],
                              text=True, capture_output=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), self.command('status')[1])

    def test_help_imports_no_gui_broker_or_llm(self):
        program = '''import sys
from shnifter_cli import build_parser
build_parser().parse_args(['paper-events','status','--db','does-not-exist'])
assert not any(n.startswith(('PySide6','ibapi','alpaca','openai','torch')) for n in sys.modules)
print('ok')'''
        proc = subprocess.run([sys.executable, '-c', program], text=True, capture_output=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), 'ok')

    def test_live_subcommand_does_not_exist(self):
        with self.assertRaises(SystemExit) as error:
            self.command('live')
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
