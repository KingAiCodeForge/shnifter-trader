"""Offline deterministic simulator tests: no network, broker, Qt or live orders."""
import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd

from shnifter_replay import (
    ReplayConfig, from_dataframe, load_csv, normalise_bars, run_replay,
)


SERIES = [100, 100, 100, 99, 98, 99, 100, 101, 102, 100, 98, 96,
          98, 100, 102, 104, 98, 90]


def make_rows(closes=SERIES):
    return [
        {'date': (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
         'open': v, 'high': v + 1, 'low': v - 1,
         'close': v, 'volume': 1000}
        for i, v in enumerate(closes)
    ]


def config(**kwargs):
    return ReplayConfig(fast_window=2, slow_window=3,
                        stop_loss_pct=Decimal('.30'),
                        take_profit_pct=Decimal('.30'), **kwargs)


class TestReplay(unittest.TestCase):
    def setUp(self):
        self.bars = normalise_bars(make_rows())

    def test_next_bar_fill_and_repeatability(self):
        cfg = config(fee_bps=Decimal('0'), slippage_bps=Decimal('0'))
        a = run_replay(self.bars, cfg, ticker='AAPL')
        b = run_replay(self.bars, cfg, ticker='AAPL')
        self.assertEqual(a, b)
        self.assertEqual(a['signals'][0]['date'], '2026-01-07')
        self.assertEqual(a['fills'][0]['date'], '2026-01-08')
        self.assertEqual(a['fills'][0]['price'], 101)
        self.assertEqual(a['fills'][0]['side'], 'BUY')
        self.assertEqual(a['completed_trades'], 2)
        self.assertEqual(a['win_rate_pct'], 0)
        self.assertTrue(a['run_id'])

    def test_costs_reduce_performance(self):
        a = run_replay(self.bars, config(fee_bps=Decimal('0'),
                                         slippage_bps=Decimal('0')))
        b = run_replay(self.bars, config(fee_bps=Decimal('30'),
                                         slippage_bps=Decimal('20')))
        self.assertLess(b['final_equity'], a['final_equity'])
        self.assertTrue(any(f['fee'] > 0 for f in b['fills']))
        self.assertGreater(b['fills'][0]['price'], a['fills'][0]['price'])
        self.assertLess(b['fills'][1]['price'], a['fills'][1]['price'])

    def test_stop_first_when_intra_bar_path_unknown(self):
        rows = make_rows()
        rows[7]['high'] = 120
        rows[7]['low'] = 80
        cfg = ReplayConfig(fast_window=2, slow_window=3, fee_bps=Decimal(0),
                           slippage_bps=Decimal(0), stop_loss_pct=Decimal('.05'),
                           take_profit_pct=Decimal('.05'))
        result = run_replay(normalise_bars(rows), cfg)
        self.assertEqual(result['trades'][0]['exit_reason'], 'stop')
        self.assertEqual(result['trades'][0]['exit_date'], '2026-01-08')
        self.assertLess(result['trades'][0]['exit'], result['trades'][0]['entry'])

    def test_gap_through_stop_uses_gap_price_not_guaranteed_stop(self):
        rows = make_rows()
        rows[8]['open'] = 80
        rows[8]['low'] = 78
        rows[8]['high'] = 103
        cfg = ReplayConfig(fast_window=2, slow_window=3, fee_bps=Decimal(0),
                           slippage_bps=Decimal(0), stop_loss_pct=Decimal('.05'),
                           take_profit_pct=Decimal('.25'))
        result = run_replay(normalise_bars(rows), cfg)
        self.assertEqual(result['trades'][0]['exit_reason'], 'stop')
        self.assertEqual(result['trades'][0]['exit'], 80)

    def test_bad_rows_are_rejected_not_repaired(self):
        for variant in ('duplicate', 'missing', 'infinite', 'bad_high', 'negative_volume'):
            with self.subTest(variant=variant):
                rows = make_rows()
                if variant == 'duplicate':
                    rows[2]['date'] = rows[1]['date']
                elif variant == 'missing':
                    del rows[2]['close']
                elif variant == 'infinite':
                    rows[2]['open'] = float('nan')
                elif variant == 'bad_high':
                    rows[2]['high'] = 50
                elif variant == 'negative_volume':
                    rows[2]['volume'] = -1
                with self.assertRaises(ValueError):
                    normalise_bars(rows)
        with self.assertRaises(ValueError):
            normalise_bars([])

    def test_invalid_strategy_constraints(self):
        with self.assertRaises(ValueError):
            run_replay(self.bars, config(max_position_pct=Decimal('1.1')))
        with self.assertRaises(ValueError):
            run_replay(self.bars, ReplayConfig(fast_window=50, slow_window=20))
        with self.assertRaises(ValueError):
            run_replay(self.bars[:3], ReplayConfig(fast_window=2, slow_window=3))

    def test_mark_to_market_without_fake_closing_trade(self):
        bars = normalise_bars(make_rows()[:9])
        result = run_replay(bars, config())
        self.assertIsNotNone(result['open_position'])
        self.assertEqual(result['completed_trades'], 0)
        self.assertIsNone(result['win_rate_pct'])
        self.assertEqual(result['fills'][0]['side'], 'BUY')
        self.assertNotEqual(result['unrealised_pnl'], 0)
        self.assertGreater(result['final_equity'], 0)

    def test_drawdown_kills_new_entries(self):
        cfg = ReplayConfig(fast_window=2, slow_window=3,
                           max_position_pct=Decimal('.95'),
                           max_drawdown_pct=Decimal('.01'),
                           stop_loss_pct=Decimal('.95'),
                           take_profit_pct=Decimal('.95'),
                           fee_bps=Decimal(0), slippage_bps=Decimal(0))
        result = run_replay(self.bars, cfg)
        self.assertTrue(result['halted'])
        self.assertIn('HALT', [s['decision'] for s in result['signals']])
        first_halt = next(i for i,s in enumerate(result['signals']) if s['decision'] == 'HALT')
        self.assertFalse(any(s['decision'] == 'BUY' for s in result['signals'][first_halt+1:]))

    def test_flat_and_multiindex_dataframe(self):
        frame = pd.DataFrame({k: [r[k] for r in make_rows()]
                              for k in ('open', 'high', 'low', 'close', 'volume')},
                             index=pd.to_datetime([r['date'] for r in make_rows()]))
        self.assertEqual(from_dataframe(frame), self.bars)
        frame.columns = pd.MultiIndex.from_tuples(
            [(str(k).title(), 'AAPL') for k in frame.columns]
        )
        self.assertEqual(from_dataframe(frame), self.bars)

    def test_csv_fixture_and_replay_audit(self):
        rows = make_rows()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'prices.csv'
            with path.open('w', newline='', encoding='utf-8') as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader()
                writer.writerows(rows)
            replay = run_replay(load_csv(path), config())
        self.assertEqual(replay['ticker'], 'UNKNOWN')
        self.assertTrue(json.dumps(replay, allow_nan=False))
        self.assertEqual(len(replay['equity_curve']), len(rows))
        ids = [f['id'] for f in replay['fills']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(t['id'] for t in replay['trades']))


if __name__ == '__main__':
    unittest.main()
