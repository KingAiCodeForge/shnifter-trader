"""Offline regression tests for auditable, explicitly opt-in replay registry."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from shnifter_experiments import (
    list_experiments, record_replay, verify_experiment,
)
from shnifter_replay import ReplayConfig, normalise_bars, run_replay
from shnifter_cli import main


SAMPLE_CLOSE = [100, 100, 100, 99, 98, 99, 100, 101, 102, 100,
                98, 96, 98, 100, 102, 104, 98, 90]


def example_bars():
    return normalise_bars([
        {"date": (date(2026, 1, 1) + timedelta(days=n)).isoformat(),
         "open": float(close), "high": float(close + 1),
         "low": float(close - 1), "close": float(close), "volume": 1000}
        for n, close in enumerate(SAMPLE_CLOSE)
    ])


class ExperimentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'experiments.sqlite'
        self.bars = example_bars()
        self.cfg = ReplayConfig(fast_window=2, slow_window=3)
        self.report = run_replay(self.bars, self.cfg, ticker='AAPL')

    def _write(self, **kwargs):
        return record_replay(self.db, bars=self.bars, report=self.report, **kwargs)

    def test_round_trip_verification_and_query(self):
        record = self._write(declared_source='fixture-unverified')
        self.assertTrue(self.db.exists())
        self.assertEqual(len(record['experiment_id']), 64)
        result = verify_experiment(self.db, record['experiment_id'])
        self.assertEqual(result['verification'], 'passed')
        self.assertTrue(result['ok'])
        rows = list_experiments(self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['dataset_sha256'], record['dataset_sha256'])
        self.assertEqual(rows[0]['bars'], len(self.bars))
        self.assertEqual(rows[0]['declared_source'], 'fixture-unverified')

    def test_repeated_identical_runs_deduplicate(self):
        first = self._write()
        again = self._write()
        self.assertEqual(first, again)
        self.assertEqual(len(list_experiments(self.db)), 1)

    def test_source_metadata_creates_distinct_research_identity(self):
        x = self._write(declared_source='unknown')
        y = self._write(declared_source='synthetic sample')
        self.assertNotEqual(x['experiment_id'], y['experiment_id'])
        self.assertEqual(len(list_experiments(self.db)), 2)
        self.assertEqual(x['run_id'], y['run_id'])

    def test_rejects_invented_pnl(self):
        forged = dict(self.report)
        forged['final_equity'] = 2_000_000
        with self.assertRaisesRegex(ValueError, 'differs from deterministic replay'):
            record_replay(self.db, bars=self.bars, report=forged)
        self.assertFalse(self.db.exists())

    def test_rejects_mismatched_data_snapshot(self):
        modified = list(self.bars)
        modified[4] = normalise_bars([
            {"date": "2026-01-05", "open": 96, "high": 99,
             "low": 95, "close": 98, "volume": 1000}
        ])[0]
        with self.assertRaisesRegex(ValueError, 'differs from deterministic replay'):
            record_replay(self.db, bars=modified, report=self.report)
        self.assertFalse(self.db.exists())

    def test_existing_unrelated_database_left_untouched(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute('CREATE TABLE another_service (secret TEXT)')
            conn.execute("INSERT INTO another_service VALUES ('do_not_modify')")
        with self.assertRaisesRegex(ValueError, 'not a Shnifter'):
            self._write()
        with sqlite3.connect(self.db) as conn:
            tables = [row[0] for row in conn.execute('SELECT name FROM sqlite_master WHERE type="table"')]
            value = conn.execute('SELECT secret FROM another_service').fetchone()[0]
        self.assertEqual(tables, ['another_service'])
        self.assertEqual(value, 'do_not_modify')

    def test_legacy_trading_db_protected(self):
        self.db = self.db.with_name('shnifter_trading.db')
        with self.assertRaisesRegex(ValueError, 'refusing'):
            self._write()
        self.assertFalse(self.db.exists())

    def test_readonly_queries_do_not_create_file(self):
        with self.assertRaises(FileNotFoundError):
            list_experiments(self.db)
        with self.assertRaises(FileNotFoundError):
            verify_experiment(self.db, 'a' * 64)
        self.assertFalse(self.db.exists())

    def test_update_and_delete_are_blocked(self):
        saved = self._write()
        with sqlite3.connect(self.db) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('UPDATE experiments SET run_id=? WHERE experiment_id=?',
                             ('bad', saved['experiment_id']))
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('DELETE FROM experiments WHERE experiment_id=?',
                             (saved['experiment_id'],))
        self.assertTrue(verify_experiment(self.db, saved['experiment_id'])['ok'])

    def test_tampered_report_is_detected(self):
        saved = self._write()
        with sqlite3.connect(self.db) as conn:
            conn.execute('DROP TRIGGER no_experiment_changes')
            conn.execute('UPDATE experiments SET report_json=? WHERE experiment_id=?',
                         ('{"some":"fake result"}', saved['experiment_id']))
        verdict = verify_experiment(self.db, saved['experiment_id'])
        self.assertFalse(verdict['ok'])
        self.assertEqual(verdict['verification'], 'failed')
        self.assertIn('report content hash mismatch', verdict['issues'])

    def test_invalid_source_label(self):
        for bad in ('', 'evil\nsource', 'x' * 200):
            with self.subTest(source=bad):
                with self.assertRaises(ValueError):
                    self._write(declared_source=bad)
        self.assertFalse(self.db.exists())

    def test_limit_is_bounded_and_type_checked(self):
        self._write()
        for limit in (-1, 0, 501, True, '2'):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    list_experiments(self.db, limit=limit)

    def test_cli_end_to_end_record_list_verify(self):
        csvpath = Path(self.temp.name) / 'bars.csv'
        with csvpath.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=['date','open','high','low','close','volume'])
            writer.writeheader()
            for bar in self.bars:
                writer.writerow({name:getattr(bar,name) for name in writer.fieldnames})
        base = ['backtest','run','--csv',str(csvpath),'--ticker','AAPL',
                '--fast','2','--slow','3','--registry-db',str(self.db)]
        out,err=io.StringIO(),io.StringIO()
        status=main(base,stdout=out,stderr=err)
        self.assertEqual(status,0,err.getvalue())
        self.assertTrue(json.loads(out.getvalue())['run_id'])
        self.assertIn('Experiment registered: ',err.getvalue())
        status=main(base,stdout=io.StringIO(),stderr=io.StringIO())
        self.assertEqual(status,0)
        self.assertEqual(len(list_experiments(self.db)),1)
        out,err=io.StringIO(),io.StringIO()
        status=main(['experiments','list','--registry-db',str(self.db)],stdout=out,stderr=err)
        self.assertEqual(status,0,err.getvalue())
        experiment_id=json.loads(out.getvalue())['experiments'][0]['experiment_id']
        out,err=io.StringIO(),io.StringIO()
        status=main(['experiments','verify','--registry-db',str(self.db),
                     '--id',experiment_id],stdout=out,stderr=err)
        self.assertEqual(status,0,err.getvalue())
        self.assertTrue(json.loads(out.getvalue())['ok'])

    def test_cli_does_not_record_if_output_path_conflicts(self):
        csvpath = Path(self.temp.name)/'bars.csv'
        with csvpath.open('w',newline='',encoding='utf-8') as stream:
            writer=csv.DictWriter(stream,fieldnames=['date','open','high','low','close','volume'])
            writer.writeheader()
            for bar in self.bars:
                writer.writerow({name:getattr(bar,name) for name in writer.fieldnames})
        target=Path(self.temp.name)/'output.json'
        target.write_text('keep',encoding='utf-8')
        out,err=io.StringIO(),io.StringIO()
        status=main(['backtest','run','--csv',str(csvpath),'--ticker','AAPL',
                     '--fast','2','--slow','3','--registry-db',str(self.db),
                     '--output',str(target)],stdout=out,stderr=err)
        self.assertEqual(status,1)
        self.assertFalse(self.db.exists())
        self.assertEqual(target.read_text(encoding='utf-8'),'keep')


if __name__ == '__main__':
    unittest.main()
