import argparse
import csv
import io
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from shnifter_backtest_cli import register_backtest, execute_backtest


class TestBacktestCLI(unittest.TestCase):
    def make_parser(self):
        parser = argparse.ArgumentParser()
        group = parser.add_subparsers(dest='group', required=True)
        register_backtest(group.add_parser('backtest'))
        return parser

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv = Path(self.tmp.name) / 'ohlcv.csv'
        with self.csv.open('w', newline='', encoding='utf-8') as fh:
            writer = csv.writer(fh)
            writer.writerow(['date', 'open', 'high', 'low', 'close', 'volume'])
            closes = [100,100,100,99,98,99,100,101,102,100,98,96,98,100,102,104,98,90]
            for i,v in enumerate(closes):
                writer.writerow([date(2026,1,1)+timedelta(days=i),v,v+1,v-1,v,1000])

    def command(self, additional=None):
        args = self.make_parser().parse_args(['backtest','run','--csv',str(self.csv),
                                               '--ticker','AAPL','--fast','2',
                                               '--slow','3',*(additional or [])])
        out, err = io.StringIO(), io.StringIO()
        status = execute_backtest(args,stdout=out,stderr=err)
        return status,out.getvalue(),err.getvalue()

    def test_cli_reports_auditable_backtest(self):
        status,out,err=self.command()
        self.assertEqual(status,0,err)
        data=json.loads(out)
        self.assertTrue(data['ok'])
        self.assertEqual(data['ticker'],'AAPL')
        self.assertGreater(len(data['fills']),0)
        self.assertEqual(data['engine'],'shnifter.sma.next-open.v1')
        self.assertEqual(data['run_id'],json.loads(self.command()[1])['run_id'])

    def test_bad_csv_or_invalid_windows_are_nonzero(self):
        status,out,err=self.command(['--slow','1'])
        self.assertEqual(status,1)
        self.assertFalse(out)
        self.assertIn('fast_window',err)
        status,out,err=self.command(['--csv',str(self.csv.with_name('missing.csv'))])
        self.assertEqual(status,1)
        self.assertFalse(out)

    def test_output_path_no_implicit_overwrite(self):
        report=Path(self.tmp.name)/'report.json'
        report.write_text('keep')
        status,out,err=self.command(['--output',str(report)])
        self.assertEqual(status,1)
        self.assertEqual(report.read_text(),'keep')
        status,out,err=self.command(['--output',str(report),'--overwrite'])
        self.assertEqual(status,0,err)
        self.assertEqual(json.loads(out)['run_id'],json.loads(report.read_text())['run_id'])

    def test_parser_rejects_invalid_percentages(self):
        status,out,err=self.command(['--fee-bps','-20'])
        self.assertEqual(status,1)
        self.assertFalse(out)
        self.assertIn('fee_bps',err)

    def test_output_mode_conflict_has_usage_exit(self):
        status,out,err=self.command(['--overwrite'])
        self.assertEqual(status,2)
        self.assertFalse(out)


if __name__=='__main__': unittest.main()
