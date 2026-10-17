"""Fail-closed offline risk helper tests; no broker, data feed or GUI."""
import math
import unittest

from core.shnifter_trade import Trade, Portfolio
from core.shnifter_risk import (
    calculate_position_size, size_from_stop_distance,
    get_portfolio_heat, check_drawdown,
)


class RiskGuardTests(unittest.TestCase):
    def test_standard_long_exposure(self):
        p = Portfolio(10_000)
        p.add_trade(Trade('AAPL', 100, 10, 90, 120))
        self.assertAlmostEqual(get_portfolio_heat(p, {}), 0.01)

    def test_short_stop_exposure(self):
        p = Portfolio(10_000)
        t = Trade('AAPL', 100, 20, 110, 80)
        t.direction = 'short'
        p.add_trade(t)
        self.assertAlmostEqual(get_portfolio_heat(p, {}), 0.02)

    def test_unknown_stop_means_unbounded_risk(self):
        p = Portfolio(10_000)
        p.add_trade(Trade('AAPL', 100, 2, None, None))
        self.assertTrue(math.isinf(get_portfolio_heat(p, {})))

    def test_wrong_side_stop_or_unknown_direction(self):
        for direction, stop in [('long', 105), ('short', 95), ('other', 90)]:
            with self.subTest(direction=direction, stop=stop):
                p = Portfolio(10_000)
                trade = Trade('AAPL', 100, 2, stop, 110)
                trade.direction = direction
                p.add_trade(trade)
                self.assertTrue(math.isinf(get_portfolio_heat(p, {})))

    def test_bad_balance_never_masks_exposure(self):
        for balance in (0, -1, float('nan'), float('inf'), None):
            with self.subTest(balance=balance):
                p = Portfolio(balance)
                p.add_trade(Trade('AAPL', 100, 2, 90, 110))
                self.assertEqual(get_portfolio_heat(p, {}), math.inf)

    def test_zero_position_with_valid_cash_is_zero_risk(self):
        self.assertEqual(get_portfolio_heat(Portfolio(1000), {}), 0)

    def test_bad_drawdown_fails_closed(self):
        p = Portfolio(1000)
        for bad in (None, float('nan'), float('inf'), -0.1, 1.1):
            with self.subTest(value=bad):
                p.max_drawdown = bad
                self.assertTrue(check_drawdown(p))
        p.max_drawdown = 0.1
        self.assertFalse(check_drawdown(p, max_drawdown=0.2))
        self.assertTrue(check_drawdown(p, max_drawdown=float('nan')))

    def test_confidence_does_not_inflate_cash_risk(self):
        a = calculate_position_size(.01, 10000)
        b = calculate_position_size(.99, 10000)
        self.assertEqual(a, b)
        self.assertEqual(a, 100)

    def test_sizing_rejects_booleans(self):
        with self.assertRaises(ValueError):
            calculate_position_size(0.9, True)
        with self.assertRaises(ValueError):
            size_from_stop_distance(capital=10000, entry_price=100,
                                    stop_price=90, max_risk_fraction=True)

    def test_numpy_real_values_supported(self):
        import numpy as np
        self.assertEqual(calculate_position_size(.5, np.float64(10000)), 100)
        p = Portfolio(np.float64(10000))
        p.add_trade(Trade('AAPL', np.float64(100), 10, np.float64(90), 120))
        self.assertAlmostEqual(get_portfolio_heat(p, {}), 0.01)

    def test_stop_distance_sizing_stays_bounded(self):
        size = size_from_stop_distance(capital=10000, entry_price=100,
                                       stop_price=95, max_risk_fraction=.01,
                                       max_position_fraction=.20)
        self.assertEqual(size, 20)


if __name__=='__main__': unittest.main()
