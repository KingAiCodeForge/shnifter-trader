"""Regression tests: LLM confidence cannot raise the trading risk budget."""
import unittest

from core.shnifter_risk import calculate_position_size, size_from_stop_distance


class RiskSizingTests(unittest.TestCase):
    def test_confidence_does_not_increase_sizing(self):
        a = calculate_position_size(0.10, 10000, 0.01)
        b = calculate_position_size(0.95, 10000, 0.01)
        self.assertEqual(a, b)
        self.assertEqual(a, 100.0)

    def test_sized_by_stop_and_gross_exposure(self):
        self.assertEqual(size_from_stop_distance(
            capital=10000, entry_price=100, stop_price=95), 20)
        self.assertEqual(size_from_stop_distance(
            capital=10000, entry_price=100, stop_price=80), 5)

    def test_invalid_risk_rejected(self):
        for p in (-1, float('nan'), 0, 0.9):
            with self.subTest(p=p):
                with self.assertRaises(ValueError):
                    calculate_position_size(None, 10000, p)
        with self.assertRaises(ValueError):
            size_from_stop_distance(capital=10000, entry_price=100, stop_price=100)


if __name__ == "__main__":
    unittest.main()
