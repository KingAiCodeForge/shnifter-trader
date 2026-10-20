"""Research integrity regressions; all prices and performance are synthetic."""
from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import subprocess
import sys
import unittest
from dataclasses import asdict, replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from shnifter_cli import main
from shnifter_oos_gate import GatePolicy, _buy_hold, evaluate_oos
from shnifter_replay import normalise_bars
from shnifter_safe_output import atomic_write_text, validate_output


def prices(n=600):
    return normalise_bars([
        dict(date=(date(2024, 1, 1) + timedelta(days=i)).isoformat(),
             open=100, high=101, low=99, close=100, volume=1000)
        for i in range(n)
    ])


def save_csv(path, data):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['date', 'open', 'high', 'low', 'close', 'volume'])
        writer.writeheader()
        writer.writerows(asdict(row) for row in data)


class BenchmarkTests(unittest.TestCase):
    def test_first_bar_loss_is_in_drawdown(self):
        rows = normalise_bars([
            dict(date='2026-01-02', open=100, high=100, low=80, close=80, volume=1000),
            dict(date='2026-01-05', open=80, high=80, low=80, close=80, volume=1000),
        ])
        result = _buy_hold(rows, 0, 2, GatePolicy(fee_bps=0, slippage_bps=0))
        self.assertEqual(result['return_pct'], -4)
        self.assertEqual(result['max_drawdown_pct'], 4)
        self.assertEqual(result['final_equity'], 9600)

    def test_first_bar_fees_cannot_disappear_from_drawdown(self):
        result = _buy_hold(prices(2), 0, 2, GatePolicy(slippage_bps=0))
        self.assertLess(result['return_pct'], 0)
        self.assertAlmostEqual(result['max_drawdown_pct'], -result['return_pct'])

    def test_benchmark_cost_rounding_has_hand_calculated_receipt(self):
        result = _buy_hold(prices(2), 0, 2, GatePolicy())
        # 19 shares * 100.05 + 1.90 commission, remainder kept in cash.
        self.assertEqual(result['shares'], 19)
        self.assertEqual(result['entry_price'], 100.05)
        self.assertEqual(result['entry_fee'], 1.90)
        self.assertEqual(result['cash'], 8097.15)
        self.assertEqual(result['final_equity'], 9997.15)
        self.assertEqual(result['max_drawdown_pct'], .0285)

    def test_cannot_afford_share_keeps_cash(self):
        rows = normalise_bars([
            dict(date='2026-01-02', open=50000, high=50001, low=49999, close=50000, volume=1000),
            dict(date='2026-01-05', open=50000, high=50001, low=49999, close=50000, volume=1000),
        ])
        result = _buy_hold(rows, 0, 2, GatePolicy())
        self.assertEqual(result['shares'], 0)
        self.assertEqual(result['entry_fee'], 0)
        self.assertEqual(result['return_pct'], 0)
        self.assertEqual(result['max_drawdown_pct'], 0)

    def test_stress_benchmark_is_present_and_cost_consistent(self):
        result = evaluate_oos(prices(), ticker='AAPL')
        for fold in result['folds']:
            base = fold['test']['buy_and_hold']
            stress = fold['test']['stressed_buy_and_hold']
            self.assertLess(stress['return_pct'], base['return_pct'])
            self.assertGreater(stress['max_drawdown_pct'], base['max_drawdown_pct'])
        self.assertFalse(result['summary']['live_authorized'])

    def test_zero_cost_stress_is_identical(self):
        policy = GatePolicy(fee_bps=0, slippage_bps=0)
        self.assertEqual(_buy_hold(prices(2), 0, 2, policy),
                         _buy_hold(prices(2), 0, 2, policy, True))

    def test_gate_accepts_normal_numeric_inputs_as_decimals(self):
        for value in (10, 10.0, '10', Decimal('10')):
            with self.subTest(value=value):
                policy = GatePolicy(fee_bps=value)
                policy.validate()
                self.assertIsInstance(policy.fee_bps, Decimal)
        self.assertEqual(GatePolicy(fee_bps='10').fee_bps, GatePolicy().fee_bps)

    def test_money_bools_and_nonfinite_values_are_not_risk_values(self):
        for field in ('fee_bps', 'slippage_bps', 'initial_cash', 'max_position_pct'):
            for value in (True, False, None, 'NaN', 'Infinity', [], 'oops'):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    GatePolicy(**{field: value})

    def test_duplicate_candidates_rejected_for_direct_api_use(self):
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            GatePolicy(candidates=((5, 20), (5, 20))).validate()

    def test_wrong_policy_type_and_oversized_controls_rejected(self):
        with self.assertRaises(ValueError):
            evaluate_oos(prices(), ticker='AAPL', policy={})
        for policy in (GatePolicy(min_prior_bars=10001),
                       GatePolicy(min_total_completed_trades=100001),
                       GatePolicy(folds=True)):
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                policy.validate()


class OutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'prices.csv'
        self.source.write_text('original input', encoding='utf-8')
        self.output = self.root / 'report.json'

    def test_new_output_is_complete_utf8(self):
        atomic_write_text(self.output, '{"note":"α"}\n')
        self.assertEqual(json.loads(self.output.read_text(encoding='utf-8'))['note'], 'α')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_refuses_existing_file_without_permission(self):
        self.output.write_text('keep')
        with self.assertRaises(FileExistsError):
            atomic_write_text(self.output, 'new')
        self.assertEqual(self.output.read_text(), 'keep')

    def test_explicit_replacement(self):
        self.output.write_text('old')
        atomic_write_text(self.output, 'new', overwrite=True)
        self.assertEqual(self.output.read_text(), 'new')

    def test_refuses_source_path_and_hard_link(self):
        self.output.hardlink_to(self.source)
        for output in (self.source, self.output):
            with self.subTest(output=output), self.assertRaises(ValueError):
                atomic_write_text(output, 'new', overwrite=True, protected=[self.source])
        self.assertEqual(self.source.read_text(), 'original input')

    def test_refuses_symlink_including_dangling_link(self):
        for target in (self.source, self.root / 'missing.csv'):
            with self.subTest(target=target):
                self.output.symlink_to(target)
                with self.assertRaises(ValueError):
                    atomic_write_text(self.output, 'new', overwrite=True)
                self.output.unlink()

    def test_refuses_directory_output_and_missing_parent(self):
        for output in (self.root, self.root / 'missing' / 'result.json'):
            with self.subTest(output=output), self.assertRaises(ValueError):
                atomic_write_text(output, 'new', overwrite=True)

    def test_fsync_failure_preserves_previous_report(self):
        self.output.write_text('old')
        with patch('shnifter_safe_output.os.fsync', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                atomic_write_text(self.output, 'new', overwrite=True)
        self.assertEqual(self.output.read_text(), 'old')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_publish_failure_cleans_temp_and_preserves_output(self):
        self.output.write_text('old')
        with patch('shnifter_safe_output.os.replace', side_effect=OSError('denied')):
            with self.assertRaises(OSError):
                atomic_write_text(self.output, 'new', overwrite=True)
        self.assertEqual(self.output.read_text(), 'old')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_racing_new_output_is_not_clobbered(self):
        original_link = os.link
        def racing_link(src, dst):
            Path(dst).write_text('concurrent owner')
            return original_link(src, dst)
        with patch('shnifter_safe_output.os.link', side_effect=racing_link):
            with self.assertRaises(FileExistsError):
                atomic_write_text(self.output, 'our report')
        self.assertEqual(self.output.read_text(), 'concurrent owner')
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_bad_payload_never_opens_output(self):
        for text in (None, 42, '\ud800'):
            with self.subTest(text=repr(text)), self.assertRaises((ValueError, UnicodeError)):
                atomic_write_text(self.output, text)
        self.assertFalse(self.output.exists())


class CLIContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.csv = self.root / 'prices.csv'
        save_csv(self.csv, prices())
        self.gate = ['research', 'gate', '--csv', str(self.csv), '--ticker', 'AAPL']

    def run_command(self, command):
        output, error = io.StringIO(), io.StringIO()
        rc = main(command, stdout=output, stderr=error)
        return rc, output.getvalue(), error.getvalue()

    def test_compact_json_preserves_identity_and_reasons(self):
        rc, full, err = self.run_command(self.gate)
        self.assertEqual(rc, 0, err)
        rc, compact, err = self.run_command(self.gate + ['--summary-only'])
        self.assertEqual(rc, 0, err)
        a, b = json.loads(full), json.loads(compact)
        self.assertEqual(a['evaluation_id'], b['evaluation_id'])
        self.assertEqual(a['summary'], b['summary'])
        self.assertNotIn('folds', b)
        self.assertEqual(b['detail_level'], 'summary')
        self.assertLess(len(compact), len(full))

    def test_rejected_screen_has_distinct_optional_exit_code(self):
        rc, text, err = self.run_command(self.gate + ['--fail-on-rejection'])
        self.assertEqual(rc, 3, err)
        self.assertTrue(json.loads(text)['ok'])
        self.assertFalse(json.loads(text)['summary']['live_authorized'])
        self.assertFalse(json.loads(text)['summary']['paper_research_candidate'])

    def test_rejected_screen_can_still_save_its_report(self):
        output = self.root / 'rejection.json'
        rc, ack, err = self.run_command(self.gate + [
            '--fail-on-rejection', '--summary-only', '--output', str(output)])
        self.assertEqual(rc, 3, err)
        self.assertFalse(json.loads(ack)['live_authorized'])
        self.assertEqual(json.loads(ack)['evaluation_id'],
                         json.loads(output.read_text())['evaluation_id'])

    def test_all_three_csv_commands_preserve_source_and_hard_links(self):
        before = self.csv.read_bytes()
        alias = self.root / 'alias.json'
        alias.hardlink_to(self.csv)
        commands = [self.gate,
                    ['analysis', 'signals', '--csv', str(self.csv), '--ticker', 'AAPL', '--no-ml'],
                    ['backtest', 'run', '--csv', str(self.csv), '--ticker', 'AAPL']]
        for command in commands:
            for output in (self.csv, alias):
                with self.subTest(command=command[:2], output=output):
                    rc, text, err = self.run_command(command + ['--output', str(output), '--overwrite'])
                    self.assertEqual(rc, 1, (text, err))
                    self.assertEqual(text, '')
                    self.assertEqual(self.csv.read_bytes(), before)

    def test_gate_preflights_output_before_expensive_evaluation(self):
        report = self.root / 'existing.json'
        report.write_text('keep')
        with patch('shnifter_oos_gate.evaluate_oos') as evaluate:
            rc, _, _ = self.run_command(self.gate + ['--output', str(report)])
            self.assertEqual(rc, 1)
            evaluate.assert_not_called()

    def test_registry_and_its_wal_sidecar_cannot_be_report_targets(self):
        db = self.root / 'experiments.sqlite'
        for target in (db, Path(str(db) + '-wal'), Path(str(db) + '-shm')):
            with self.subTest(target=target):
                rc, _, _ = self.run_command([
                    'backtest', 'run', '--csv', str(self.csv), '--ticker', 'AAPL',
                    '--registry-db', str(db), '--output', str(target), '--overwrite'])
                self.assertEqual(rc, 1)
                self.assertFalse(db.exists())

    def test_runtime_error_remains_distinct_from_rejection(self):
        rc, out, err = self.run_command(self.gate + [
            '--csv', str(self.root / 'missing.csv'), '--fail-on-rejection'])
        self.assertEqual(rc, 1)
        self.assertEqual(out, '')
        self.assertIn('failed', err)

    def test_real_process_exit_and_stdout_contract(self):
        entry = Path(__file__).resolve().parents[1] / 'shnifter_cli.py'
        run = subprocess.run([sys.executable, str(entry), *self.gate,
                              '--summary-only', '--fail-on-rejection'],
                             capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 3, run.stderr)
        self.assertFalse(json.loads(run.stdout)['summary']['live_authorized'])

    def test_help_works_from_a_fresh_process(self):
        entry = Path(__file__).resolve().parents[1] / 'shnifter_cli.py'
        run = subprocess.run([sys.executable, str(entry), 'research', 'gate', '--help'],
                             capture_output=True, text=True, timeout=15)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('--fail-on-rejection', run.stdout)
        self.assertIn('--summary-only', run.stdout)

    def test_overwrite_requires_output(self):
        rc, out, err = self.run_command(self.gate + ['--overwrite'])
        self.assertEqual(rc, 2)
        self.assertEqual(out, '')
        self.assertIn('requires', err)


if __name__ == '__main__':
    unittest.main()
