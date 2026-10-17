"""Offline walk-forward checks; synthetic data is NOT evidence of market alpha."""
import csv
import io
import json
import math
import tempfile
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from shnifter_replay import normalise_bars
from shnifter_oos_gate import GatePolicy, evaluate_oos
from shnifter_cli import main


def bars(length=600, *, mode='wave'):
    rows=[]
    for i in range(length):
        close = (100 + 0.02*i + 5*math.sin(.11*i)) if mode=='wave' else 100.
        rows.append({'date':(date(2024,1,1)+timedelta(days=i)).isoformat(),
                     'open':close,'high':close+1,'low':close-1,
                     'close':close,'volume':1000})
    return normalise_bars(rows)


class OOSGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.example=bars()

    def test_three_expanding_folds_are_chronological(self):
        report=evaluate_oos(self.example,ticker='AAPL')
        self.assertEqual(len(report['folds']),3)
        self.assertFalse(report['summary']['live_authorized'])
        self.assertEqual(report['engine'],'shnifter.oos-fold-evaluator.v1')
        for fold in report['folds']:
            self.assertEqual(fold["prior_history_end_exclusive"], fold["validation"]["start"])
            self.assertLess(fold['validation']['end'],fold['test']['start'])
            self.assertEqual(len(fold['validation']['standings']),4)
        self.assertEqual(report['folds'][0]['test']['end'],report['folds'][1]['validation']['end'])

    def test_repeatability(self):
        self.assertEqual(evaluate_oos(self.example,ticker='AAPL'),
                         evaluate_oos(self.example,ticker='AAPL'))

    def test_last_test_period_does_not_change_any_selection(self):
        baseline=evaluate_oos(self.example,ticker='AAPL')
        altered=[]
        for i,bar in enumerate(self.example):
            row=dict(date=bar.date,open=bar.open, high=bar.high,
                     low=bar.low, close=bar.close,volume=bar.volume)
            if i>=len(self.example)-80:
                price=float(bar.close)*1.6
                row.update(open=price,close=price,high=price+2,low=price-2)
            altered.append(row)
        changed=evaluate_oos(normalise_bars(altered),ticker='AAPL')
        self.assertEqual([r['selected'] for r in baseline['folds']],
                         [r['selected'] for r in changed['folds']])
        self.assertEqual([r['validation'] for r in baseline['folds']],
                         [r['validation'] for r in changed['folds']])
        self.assertNotEqual(baseline['folds'][-1]['test']['buy_and_hold'],
                            changed['folds'][-1]['test']['buy_and_hold'])

    def test_invalid_small_history_fails(self):
        with self.assertRaisesRegex(ValueError,'not enough chronological'):
            evaluate_oos(self.example[:220],ticker='AAPL')

    def test_invalid_ticker(self):
        with self.assertRaises(ValueError):
            evaluate_oos(self.example,ticker='AAPL MSFT')

    def test_wrong_costs_fail(self):
        with self.assertRaises(ValueError):
            evaluate_oos(self.example,ticker='AAPL',policy=GatePolicy(fee_bps=Decimal('-1')))

    def test_bad_candidates_fail(self):
        with self.assertRaises(ValueError):
            evaluate_oos(self.example,ticker='AAPL',policy=GatePolicy(candidates=((30,10),)))

    def test_no_alpha_flat_series_does_not_pass(self):
        out=evaluate_oos(bars(mode='flat'),ticker='AAPL')
        self.assertFalse(out['summary']['paper_research_candidate'])
        self.assertIn('insufficient completed trades',out['summary']['rejection_reasons'])

    def test_stress_cost_does_not_improve_on_zero_costs(self):
        out=evaluate_oos(self.example,ticker='AAPL',policy=GatePolicy(fee_bps=Decimal('0'),slippage_bps=Decimal('0')))
        self.assertTrue(all(f['test']['strategy']['return_pct']==f['test']['stressed_costs']['return_pct']
                            for f in out['folds']))
        priced=evaluate_oos(self.example,ticker='AAPL')
        self.assertTrue(all(f['test']['stressed_costs']['return_pct']<=f['test']['strategy']['return_pct']
                            for f in priced['folds']))

    def test_benchmark_is_allocated_not_fully_invested(self):
        flat=evaluate_oos(bars(mode='flat'),ticker='AAPL')
        for f in flat['folds']:
            self.assertLessEqual(f['test']['buy_and_hold']['shares'],20)
            self.assertLess(f['test']['buy_and_hold']['return_pct'],0)

    def test_zero_fractional_share_or_negative_cash_rejected(self):
        for pct in (Decimal('0'),Decimal('1.1')):
            with self.assertRaises(ValueError):
                evaluate_oos(self.example,ticker='AAPL',policy=GatePolicy(max_position_pct=pct))

    def test_user_input_csv_cli_and_nonoverwriting_output(self):
        with tempfile.TemporaryDirectory() as directory:
            csv_file=Path(directory)/'prices.csv'
            with csv_file.open('w',newline='',encoding='utf-8') as fh:
                w=csv.DictWriter(fh,fieldnames=['date','open','high','low','close','volume']);w.writeheader()
                for b in self.example:w.writerow({key:getattr(b,key) for key in w.fieldnames})
            args=['research','gate','--csv',str(csv_file),'--ticker','AAPL']
            out,err=io.StringIO(),io.StringIO()
            self.assertEqual(main(args,stdout=out,stderr=err),0,err.getvalue())
            self.assertFalse(json.loads(out.getvalue())['summary']['live_authorized'])
            path=Path(directory)/'gate.json';path.write_text('leave me')
            self.assertEqual(main(args+['--output',str(path)],stdout=io.StringIO(),stderr=io.StringIO()),1)
            self.assertEqual(path.read_text(),'leave me')
            self.assertEqual(main(args+['--output',str(path),'--overwrite'],stdout=io.StringIO(),stderr=io.StringIO()),0)
            self.assertTrue(json.loads(path.read_text())['ok'])
            self.assertEqual(main(args+['--output',str(csv_file),'--overwrite'],stdout=io.StringIO(),stderr=io.StringIO()),1)

    def test_cli_validates_grid_flags(self):
        from shnifter_research_cli import parse_pairs
        self.assertEqual(parse_pairs('5:20,20:100'),((5,20),(20,100)))
        for bad in ('30:10','5:20,5:20','1:10','999:1000'):
            with self.subTest(bad=bad),self.assertRaises(Exception):parse_pairs(bad)


if __name__=='__main__':unittest.main()
