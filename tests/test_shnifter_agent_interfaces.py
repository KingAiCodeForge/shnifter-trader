"""No-network, no-broker tests for headless signals and agent adapters."""
from __future__ import annotations

import csv
import io
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from shnifter_actions import invoke_action, list_actions
from shnifter_analysis_core import evaluate_signals
from shnifter_agent_cli import register_actions, run_action


def synthetic_rows(n=180):
    rows = []
    d0 = date(2026, 1, 1)
    # deterministic bidirectional movement, not a real strategy backtest
    for i in range(n):
        close = 100.0 + 0.05 * i + 4.0 * __import__('math').sin(i * .22)
        rows.append({'date': (d0 + timedelta(days=i)).isoformat(),
                     'open': close - .2, 'high': close + 1,
                     'low': close - 1, 'close': close, 'volume': 1000})
    return rows


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.rows = synthetic_rows()
        self.df = pd.DataFrame(self.rows).set_index('date')

    def test_headless_signal_preserves_unknown_last_target(self):
        result = evaluate_signals(self.df, ticker='aapl')
        self.assertEqual(result['ticker'], 'AAPL')
        self.assertEqual(result['execution_permission'], 'research_only')
        self.assertEqual(result['ml']['status'], 'evaluated')
        self.assertEqual(result['ml']['last_labeled_bar'], self.rows[-2]['date'])
        self.assertEqual(result['ml']['test_samples'] > 0, True)
        self.assertLess(result['ml']['train_last_bar'], result['ml']['test_first_bar'])
        self.assertNotEqual(result['ml']['train_last_bar'], result['ml']['last_training_target_bar'])
        self.assertTrue(0 <= result['ml']['probability_up_uncalibrated'] <= 1)

    def test_synthetic_repeatability(self):
        first = evaluate_signals(self.df, ticker='AAPL')
        second = evaluate_signals(self.df, ticker='AAPL')
        self.assertEqual(first, second)

    def test_only_trend_can_respond_on_small_data(self):
        result = evaluate_signals(self.df.iloc[:65], ticker='AAPL')
        self.assertEqual(result['ml']['status'], 'insufficient_data')
        self.assertIsNone(result['ml']['probability_up_uncalibrated'])
        self.assertEqual(result['consensus'], 'HOLD')

    def test_offline_disabled_ml_does_not_import_model(self):
        result = evaluate_signals(self.df, ticker='AAPL', use_ml=False)
        self.assertEqual(result['ml']['status'], 'disabled')
        self.assertEqual(result['consensus'], 'HOLD')

    def test_invalid_inputs_are_rejected(self):
        for bad in [[], self.rows[:2]]:
            if not bad:
                with self.assertRaises(ValueError):
                    invoke_action('analysis.signals', {'ticker': 'AAPL', 'rows': bad})
        for fast, slow in [(50,20),(2,251),(0,50)]:
            with self.subTest(fast=fast,slow=slow):
                with self.assertRaises(ValueError):
                    evaluate_signals(self.df, ticker='AAPL', fast=fast, slow=slow)
        bad = self.df.copy()
        bad.iloc[-1, bad.columns.get_loc('close')] = float('nan')
        with self.assertRaises(ValueError):
            evaluate_signals(bad, ticker='AAPL')

    def test_action_catalogue_and_no_order_routes(self):
        found = list_actions()
        self.assertEqual({x['name'] for x in found},
                         {'actions.list','market.historical','analysis.signals','backtest.replay'})
        self.assertTrue(all(x['capability']=='read_only' for x in found))
        for candidate in ('paper.order','broker.submit_order','live.buy'):
            with self.assertRaises(ValueError):
                invoke_action(candidate, {'ticker':'AAPL'})

    def test_action_shared_analysis_and_replay(self):
        sig=invoke_action('analysis.signals', {'ticker':'AAPL','rows':self.rows})
        self.assertEqual(sig['result']['ml']['status'],'evaluated')
        replay=invoke_action('backtest.replay', {'ticker':'AAPL','rows':self.rows})
        self.assertEqual(replay['result']['engine'], 'shnifter.sma.next-open.v1')
        self.assertTrue(replay['result']['run_id'])
        self.assertEqual(replay['result']['bars'],len(self.rows))

    def test_market_action_mocked_no_network(self):
        prices = pd.DataFrame({"open": [100], "high": [102], "low": [99],
                               "close": [101], "volume": [1234]},
                              index=pd.to_datetime(["2026-10-01"]))
        with patch("shnifter_cli._fetch_historical", return_value=prices) as fetch:
            result = invoke_action("market.historical", {
                "ticker": "AAPL", "start": "2026-10-01", "end": "2026-10-02"})
            self.assertEqual(result["rows"][0]["close"], 101.0)
            fetch.assert_called_once()
        with self.assertRaises(ValueError):
            invoke_action("market.historical", {
                "ticker": "AAPL", "start": "2026-10-02", "end": "2026-10-01"})

    def test_action_rejects_unknown_params_and_unordered_rows(self):
        with self.assertRaises(ValueError):
            invoke_action('analysis.signals', {'ticker':'AAPL','rows':self.rows,'live':True})
        with self.assertRaises(ValueError):
            invoke_action('analysis.signals', {'ticker':'AAPL','rows':list(reversed(self.rows))})
        with self.assertRaises(ValueError):
            invoke_action('analysis.signals', {'ticker':'AAPL','rows':self.rows,'min_labeled':0})


class CLIAndHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv = Path(self.tmp.name)/'history.csv'
        self.rows=synthetic_rows()
        with self.csv.open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=['date','open','high','low','close','volume'])
            writer.writeheader(); writer.writerows(self.rows)

    def parser(self):
        import argparse
        parser=argparse.ArgumentParser()
        register_actions(parser.add_subparsers(dest='group',required=True))
        return parser

    def test_cli_list_is_json(self):
        out=io.StringIO();err=io.StringIO()
        rc=run_action(self.parser().parse_args(['actions','list']),stdout=out,stderr=err)
        self.assertEqual(rc,0,err.getvalue())
        self.assertEqual(len(json.loads(out.getvalue())['actions']),4)

    def test_cli_analyse(self):
        out=io.StringIO();err=io.StringIO()
        arg=['analysis','signals','--csv',str(self.csv),'--ticker','AAPL','--fast','10','--slow','30']
        rc=run_action(self.parser().parse_args(arg),stdout=out,stderr=err)
        self.assertEqual(rc,0,err.getvalue())
        self.assertEqual(json.loads(out.getvalue())['result']['ml']['status'],'evaluated')

    def test_cli_output_is_not_overwritten_without_permission(self):
        out=io.StringIO();err=io.StringIO(); dest=Path(self.tmp.name)/'analysis.json'
        dest.write_text('KEEP')
        arg=['analysis','signals','--csv',str(self.csv),'--ticker','AAPL','--output',str(dest)]
        rc=run_action(self.parser().parse_args(arg),stdout=out,stderr=err)
        self.assertEqual(rc,1)
        self.assertEqual(dest.read_text(),'KEEP')
        out=io.StringIO();err=io.StringIO()
        rc=run_action(self.parser().parse_args(arg+['--overwrite']),stdout=out,stderr=err)
        self.assertEqual(rc,0,err.getvalue())
        self.assertTrue(json.loads(dest.read_text())['ok'])

    def test_api_denies_untrusted_unauthenticated_clients(self):
        from fastapi.testclient import TestClient
        from shnifter_agent_api import app
        with patch.dict(os.environ, {'SHNIFTER_READONLY_API_KEY':'unit-test-key'}):
            client=TestClient(app)
            self.assertEqual(client.get('/v1/actions').status_code,401)
            self.assertEqual(client.get('/v1/actions',headers={'x-api-key':'wrong'}).status_code,401)
            authorized={'x-api-key':'unit-test-key'}
            self.assertEqual(client.get('/v1/actions',headers=authorized).status_code,200)
            self.assertEqual(client.post('/v1/actions/live.buy',json={'params':{'ticker':'AAPL'}},headers=authorized).status_code,422)
            response=client.post('/v1/actions/analysis.signals',json={'params':{'ticker':'AAPL','rows':self.rows}},headers=authorized)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['result']['execution_permission'],'research_only')


if __name__=='__main__':unittest.main()
