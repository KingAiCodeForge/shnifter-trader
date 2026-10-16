"""Tests that untrusted API/MCP arguments fail with controlled validation.

Synthetic OHLCV only, no external data and no brokerage actions.
"""
from __future__ import annotations

import math
import os
import unittest
from unittest.mock import patch

from shnifter_actions import invoke_action
from datetime import date, timedelta


def synthetic_rows(n=100):
    return [dict(date=(date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                 open=100+i*0.02, high=101+i*0.02, low=99+i*0.02,
                 close=100+i*0.02, volume=1000) for i in range(n)]


class InputGuardTests(unittest.TestCase):
    def test_market_ticker_types_fail_with_value_error(self):
        for bad in (123, None, [], {}, False):
            with self.subTest(ticker=bad):
                with self.assertRaisesRegex(ValueError, 'ticker must be a string'):
                    invoke_action('market.historical', {
                        'ticker':bad,'start':'2026-01-01','end':'2026-01-06'
                    })

    def test_market_date_types_fail_with_value_error(self):
        for key in ('start','end'):
            for bad in (123, None, True, []):
                params={'ticker':'AAPL','start':'2026-01-01','end':'2026-01-06'}
                params[key]=bad
                with self.subTest(field=key,value=bad):
                    with self.assertRaisesRegex(ValueError, key+' must be a string'):
                        invoke_action('market.historical',params)

    def test_typeless_action_and_mixed_unknown_keys_fail_closed(self):
        with self.assertRaises(ValueError):
            invoke_action(['broker.submit_order'],{})
        with self.assertRaises(ValueError):
            invoke_action('actions.list',{3:2,'bad':True})

    def test_signals_reject_malformed_option_types(self):
        rows=synthetic_rows(100)
        for params in ({'ticker':12}, {'fast':True}, {'slow':3.4},
                       {'min_labeled':'80'}, {'use_ml':'false'}, {'use_ml':0}):
            with self.subTest(parameters=params):
                with self.assertRaises(ValueError):
                    invoke_action('analysis.signals',{'ticker':'AAPL','rows':rows,**params})

    def test_backtest_rejects_boolean_window(self):
        rows=synthetic_rows(100)
        for name in ('fast','slow'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    invoke_action('backtest.replay',{'ticker':'AAPL','rows':rows,name:True})

    def test_no_order_actions_after_invalid_requests(self):
        for name in ('paper.order','broker.submit_order','live.buy'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    invoke_action(name,{'ticker':'AAPL','quantity':10})


class HttpValidationTests(unittest.TestCase):
    def test_http_errors_are_422_not_uncaught_attribute_errors(self):
        from fastapi.testclient import TestClient
        from shnifter_agent_api import app
        with patch.dict(os.environ,{'SHNIFTER_READONLY_API_KEY':'unit-test-token'}):
            c=TestClient(app)
            headers={'X-API-Key':'unit-test-token'}
            for bad in (123,None,{},[]):
                with self.subTest(ticker=bad):
                    response=c.post('/v1/actions/market.historical',headers=headers,json={
                        'params':{'ticker':bad,'start':'2026-01-01','end':'2026-01-06'}
                    })
                    self.assertEqual(response.status_code,422,response.text)
            unsupported=c.post('/v1/actions/live.buy',headers=headers,json={'params':{'ticker':'AAPL'}})
            self.assertEqual(unsupported.status_code,422)
            denied=c.get('/v1/actions')
            self.assertEqual(denied.status_code,401)


if __name__ == '__main__':
    unittest.main()
