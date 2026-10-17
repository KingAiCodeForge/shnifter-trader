"""Pure offline risk-math regression: runs without Qt, broker or data feed."""
import unittest
from decimal import Decimal

from core.safe_risk_math import amount, whole_share_size, check_proposed_order


class PureRiskMathTests(unittest.TestCase):
    def params(self, **overrides):
        arguments = dict(
            equity=10000, positions={}, symbol="AAPL", side="BUY",
            quantity=1, market_price=100, max_position_value=1000,
            max_asset_fraction=.2, max_portfolio_fraction=.8,
            daily_pnl=0, max_daily_loss=100,
        )
        arguments.update(overrides)
        return arguments

    def test_size_is_capped_by_asset_and_risk_budget(self):
        units = whole_share_size(
            equity=10000, risk_fraction=.01, entry=100, stop=95,
            max_asset_fraction=.1, max_position_value=3000)
        self.assertEqual(units, Decimal("10"))

    def test_risk_fraction_over_two_percent_rejected(self):
        with self.assertRaises(ValueError):
            whole_share_size(
                equity=10000, risk_fraction=.1, entry=100, stop=95,
                max_asset_fraction=.2, max_position_value=2000)

    def test_bad_stop_geometry_rejected(self):
        for stop in (0, 100, 101, None, float("nan"), float("inf")):
            with self.subTest(stop=stop), self.assertRaises(ValueError):
                whole_share_size(
                    equity=10000, risk_fraction=.01, entry=100, stop=stop,
                    max_asset_fraction=.2, max_position_value=2000)

    def test_basic_bounded_long_entry(self):
        self.assertTrue(check_proposed_order(**self.params())[0])

    def test_total_portfolio_projection(self):
        decision = check_proposed_order(**self.params(
            positions={"MSFT": {"value": 7950, "quantity": 79}}, quantity=1))
        self.assertFalse(decision[0])
        self.assertIn("projected portfolio", decision[1])

    def test_single_asset_projection(self):
        decision = check_proposed_order(**self.params(
            positions={"AAPL": {"value": 1900, "quantity": 19}}, quantity=2))
        self.assertFalse(decision[0])
        self.assertIn("projected asset", decision[1])

    def test_halt_blocks_entries(self):
        self.assertFalse(
            check_proposed_order(**self.params(entry_halted=True))[0])

    def test_halt_allows_only_provable_long_reductions(self):
        state = {"AAPL": {"value": 300, "quantity": 3}}
        self.assertTrue(check_proposed_order(**self.params(
            positions=state, side="SELL", quantity=2, entry_halted=True))[0])
        self.assertFalse(check_proposed_order(**self.params(
            positions=state, side="SELL", quantity=4, entry_halted=True))[0])

    def test_unowned_short_sale_rejected(self):
        self.assertFalse(check_proposed_order(**self.params(side="SELL"))[0])

    def test_bad_position_snapshots_rejected(self):
        states = (
            {"AAPL": {"value": None, "quantity": 1}},
            {"AAPL": {"value": 123}},
            {"AAPL": {"value": 100, "quantity": 0}},
            {"AAPL": {"value": 0, "quantity": 1}},
            {"AAPL": {"value": float("nan"), "quantity": 1}},
        )
        for state in states:
            with self.subTest(state=state):
                self.assertFalse(check_proposed_order(**self.params(
                    positions=state))[0])

    def test_bad_quantities_rejected(self):
        for quantity in (0, -1, True, 0.5, float("inf")):
            with self.subTest(quantity=quantity):
                self.assertFalse(check_proposed_order(**self.params(
                    quantity=quantity))[0])

    def test_bad_quotes_rejected(self):
        for quote in (0, -1, None, float("nan")):
            with self.subTest(quote=quote):
                self.assertFalse(check_proposed_order(**self.params(
                    market_price=quote))[0])

    def test_order_limit_price_guard(self):
        self.assertFalse(check_proposed_order(**self.params(
            order_price=150))[0])
        self.assertTrue(check_proposed_order(**self.params(
            order_price=101))[0])

    def test_daily_loss_rejects_entries(self):
        self.assertFalse(check_proposed_order(**self.params(
            daily_pnl=-100))[0])
        self.assertTrue(check_proposed_order(**self.params(
            daily_pnl=-99.99))[0])

    def test_nonfinite_and_unnumeric_inputs_rejected(self):
        for bad in ("NaN", "Infinity", False, None, "bad"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                amount(bad, "test")

    def test_boundary_equal_to_limit_is_allowed(self):
        self.assertTrue(check_proposed_order(**self.params(
            max_position_value=100))[0])

    def test_many_sizes_remain_within_value_and_stop_risk(self):
        for price in range(1, 150):
            for fraction in (.001, .005, .01, .02):
                units = whole_share_size(
                    equity=10000, risk_fraction=fraction, entry=price,
                    stop=price * .98, max_asset_fraction=.2,
                    max_position_value=1000)
                self.assertGreaterEqual(units, 0)
                self.assertLessEqual(units * Decimal(price), 1000)
                self.assertLessEqual(
                    units * Decimal(str(price * .02)),
                    Decimal(10000) * Decimal(str(fraction)) + Decimal(".00001"),
                )


if __name__ == "__main__":
    unittest.main()
