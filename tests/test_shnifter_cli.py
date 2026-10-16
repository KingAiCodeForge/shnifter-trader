"""Offline regression tests for the first Shnifter Trader CLI action.

These tests use synthetic OHLCV rows; they do NOT claim a live yfinance feed,
backtest, risk engine or paper-order ledger has been validated.
"""
import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from shnifter_cli import main


class TestHistoricalCLI(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.frame = pd.DataFrame(
            {
                "open": [100, 101, 102],
                "high": [102, 104, 105],
                "low": [99, 100, 101],
                "close": [101.5, 102.5, 103.5],
                "adj_close": [float("nan"), 102.5, 103.5],
                "volume": [1000, 2000, 3000],
            },
            index=pd.to_datetime(["2026-10-12", "2026-10-13", "2026-10-14"]),
        )

    def fetch(self, ticker, start, end):
        self.calls.append((ticker, start, end))
        return self.frame.copy()

    def call(self, more_args=(), *, fetcher=None):
        output, errors = io.StringIO(), io.StringIO()
        args = [
            "market", "historical", "--ticker", "aapl",
            "--start", "2026-10-12", "--end", "2026-10-15",
            *more_args,
        ]
        status = main(
            args, fetcher=fetcher or self.fetch, stdout=output, stderr=errors
        )
        return status, output.getvalue(), errors.getvalue()

    def test_json_is_structured_and_normalises_symbol(self):
        status, output, errors = self.call(["--limit", "2"])
        self.assertEqual(status, 0, errors)
        self.assertFalse(errors)
        doc = json.loads(output)
        self.assertTrue(doc["ok"])
        self.assertEqual(doc["action"], "market.historical")
        self.assertEqual(doc["provider"], "yfinance")
        self.assertEqual(doc["ticker"], "AAPL")
        self.assertEqual(doc["end_exclusive"], "2026-10-15")
        self.assertEqual(doc["count"], 2)
        self.assertEqual(doc["rows"][0]["date"], "2026-10-13")
        self.assertEqual(doc["rows"][-1]["volume"], 3000)
        self.assertEqual(self.calls, [("AAPL", "2026-10-12", "2026-10-15")])

    def test_json_missing_adjusted_price_becomes_null(self):
        status, output, _ = self.call()
        self.assertEqual(status, 0)
        rows = json.loads(output)["rows"]
        self.assertIsNone(rows[0]["adj_close"])

    def test_csv_has_stable_columns(self):
        status, output, errors = self.call(["--format", "csv", "--limit", "1"])
        self.assertEqual(status, 0, errors)
        rows = list(csv.DictReader(io.StringIO(output)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-10-14")
        self.assertEqual(rows[0]["close"], "103.5")

    def test_multiindex_columns_from_yfinance_are_normalised(self):
        self.frame.columns = pd.MultiIndex.from_tuples(
            [(name.title(), "AAPL") for name in self.frame.columns]
        )
        status, output, errors = self.call()
        self.assertEqual(status, 0, errors)
        self.assertEqual(json.loads(output)["rows"][0]["open"], 100.0)

    def test_invalid_date_range_does_not_fetch(self):
        status, output, errors = self.call(
            ["--start", "2026-10-17", "--end", "2026-10-17"]
        )
        self.assertEqual(status, 2)
        self.assertEqual(output, "")
        self.assertIn("earlier than", errors)
        self.assertEqual(self.calls, [])

    def test_empty_feed_is_nonzero_and_does_not_emit_fake_prices(self):
        status, output, errors = self.call(
            fetcher=lambda *args: pd.DataFrame()
        )
        self.assertEqual(status, 1)
        self.assertEqual(output, "")
        self.assertIn("no historical prices returned", errors)

    def test_missing_required_ohlcv_field_is_an_error(self):
        self.frame = self.frame.drop(columns=["close"])
        status, output, errors = self.call()
        self.assertEqual(status, 1)
        self.assertFalse(output)
        self.assertIn("missing required OHLCV", errors)

    def test_output_file_never_overwrites_implicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "market.json"
            dest.write_text("keep", encoding="utf-8")
            status, output, errors = self.call(["--output", str(dest)])
            self.assertEqual(status, 1)
            self.assertEqual(dest.read_text(encoding="utf-8"), "keep")
            self.assertFalse(output)
            self.assertTrue(errors)

            status, output, errors = self.call(
                ["--output", str(dest), "--overwrite"]
            )
            self.assertEqual(status, 0, errors)
            self.assertEqual(json.loads(dest.read_text())["count"], 3)
            self.assertEqual(json.loads(output)["count"], 3)

    def test_output_without_overwrite_creates_new_file(self):
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "market.csv"
            status, output, errors = self.call(
                ["--format", "csv", "--output", str(dest)]
            )
            self.assertEqual(status, 0, errors)
            self.assertTrue(dest.exists())
            with dest.open(newline="", encoding="utf-8") as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 3)
            self.assertEqual(json.loads(output)["format"], "csv")

    def test_invalid_symbol_and_limit_fail_at_argparse(self):
        for additional in (
            ["--ticker", "AAPL,MSFT"],
            ["--ticker", "../secret"],
            ["--limit", "0"],
            ["--end", "17-10-2026"],
            ["--provider", "benzinga"],
        ):
            with self.subTest(args=additional):
                with self.assertRaises(SystemExit) as caught:
                    main(
                        ["market", "historical", "--ticker", "AAPL",
                         "--start", "2026-10-12", "--end", "2026-10-15",
                         *additional],
                        fetcher=self.fetch,
                    )
                self.assertEqual(caught.exception.code, 2)
        self.assertFalse(self.calls)


if __name__ == "__main__":
    unittest.main()
