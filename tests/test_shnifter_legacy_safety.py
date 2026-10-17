"""Isolated offline regression tests for legacy risk, DB and retry safeguards.

Uses actual source files with lightweight stubs for Qt-dependent EventLog and
market data. Does not import the global data_manager or contact a broker.
"""
from __future__ import annotations

import ast
import asyncio
import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from unittest.mock import patch

from core.safe_risk_math import whole_share_size, check_proposed_order

ROOT = Path(__file__).resolve().parents[1]


class FakeLog:
    @classmethod
    def emit(cls, *args, **kwargs):
        return None


class FakeBus:
    @classmethod
    def publish(cls, *args, **kwargs):
        return None


def load_source(relative_path: str, *, strip_global_manager: bool = False):
    """Load real source in a private namespace, avoiding Qt/global writes."""
    path = ROOT / relative_path
    fake_events = types.ModuleType("core.events")
    fake_events.EventLog, fake_events.EventBus = FakeLog, FakeBus
    fake_obb = types.ModuleType("shnifterBB.shnifter_bb")
    fake_obb.ShnifterBB = type("FakeShnifterBB", (), {})
    fake_models = types.ModuleType("core.data_models")
    fake_models.ShnifterData = object
    src = path.read_text(encoding="utf-8")
    parsed = ast.parse(src, str(path))
    if strip_global_manager:
        parsed.body = [
            node for node in parsed.body
            if not (
                isinstance(node, (ast.Assign, ast.AnnAssign)) and
                any(getattr(t, "id", None) == "data_manager"
                    for t in getattr(node, "targets", [getattr(node, "target", None)]))
            )
        ]
    spec = importlib.util.spec_from_file_location(
        "_shnifter_isolated_" + path.stem, str(path))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {
        "core.events": fake_events,
        "shnifterBB.shnifter_bb": fake_obb,
        "core.data_models": fake_models,
    }):
        exec(compile(parsed, str(path), "exec"), module.__dict__)
    return module


class RiskTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.mod = load_source("core/risk_management.py")
        self.execution = load_source("core/execution.py")
        self.rm = self.mod.RiskManager(self.mod.RiskLimits(), Decimal("10000"))

    async def test_no_reconciliation_means_no_approvals(self):
        request = self.execution.OrderRequest(
            "AAPL", self.execution.OrderSide.BUY, Decimal("1"),
            self.execution.OrderType.MARKET)
        allowed, reason = await self.rm.validate_order(request, Decimal("100"))
        self.assertFalse(allowed)
        self.assertIn("no reconciled", reason)

    async def test_bounded_quantity_ignores_confidence(self):
        first = await self.rm.calculate_position_size(
            Decimal("10000"), Decimal(".01"), Decimal("100"),
            Decimal("95"), .01)
        second = await self.rm.calculate_position_size(
            Decimal("10000"), Decimal(".01"), Decimal("100"),
            Decimal("95"), .99)
        self.assertEqual(first, second)
        self.assertEqual(first, Decimal("10"))

    async def test_zero_distance_and_reverse_stop_fail_closed(self):
        for bad_stop in (Decimal("100"), Decimal("120"), Decimal("0")):
            size = await self.rm.calculate_position_size(
                Decimal("10000"), Decimal(".01"), Decimal("100"),
                bad_stop, .99)
            self.assertEqual(size, 0)

    async def test_latch_survives_date_rollover(self):
        self.rm.circuit_breaker_active = True
        self.rm.last_reset = datetime.now().date() - timedelta(days=1)
        await self.rm._reset_daily_counters()
        self.assertTrue(self.rm.circuit_breaker_active)

    async def test_projected_buy_vs_risk_reducing_sell(self):
        self.rm.position_snapshot_verified = True  # test-controlled snapshot
        self.rm.positions = {"AAPL": {"value": Decimal("1000"),
                                       "quantity": Decimal("10")}}
        buy = self.execution.OrderRequest(
            "AAPL", self.execution.OrderSide.BUY, Decimal("1"),
            self.execution.OrderType.MARKET)
        allowed, reason = await self.rm.validate_order(buy, Decimal("100"))
        self.assertFalse(allowed)
        self.assertIn("asset exposure", reason)
        self.rm.circuit_breaker_active = True
        sell = self.execution.OrderRequest(
            "AAPL", self.execution.OrderSide.SELL, Decimal("1"),
            self.execution.OrderType.MARKET)
        allowed, reason = await self.rm.validate_order(sell, Decimal("100"))
        self.assertTrue(allowed, reason)

    async def test_generic_retry_rejects_submit_even_when_transient(self):
        counter = [0]
        async def submit_order():
            counter[0] += 1
            raise ConnectionError("timeout after transmit")
        limiter = self.execution.RateLimiter(base_delay=0)
        with self.assertRaisesRegex(ValueError, "forbidden"):
            await limiter.execute_with_backoff(submit_order)
        self.assertEqual(counter[0], 0)

    async def test_read_retry_only(self):
        counter = [0]
        async def get_positions():
            counter[0] += 1
            if counter[0] == 1:
                raise TimeoutError("temporary")
            return {"AAPL": 3}
        limiter = self.execution.RateLimiter(base_delay=0)
        self.assertEqual(await limiter.execute_with_backoff(get_positions),
                         {"AAPL": 3})
        self.assertEqual(counter[0], 2)

    async def test_risk_math_fails_invalid_and_projected_total(self):
        result = check_proposed_order(
            equity=10000, positions={"MSFT": {"value": 7900, "quantity": 79}},
            symbol="AAPL", side="BUY", quantity=2, market_price=100,
            max_position_value=1000, max_asset_fraction=.2,
            max_portfolio_fraction=.8, daily_pnl=0, max_daily_loss=100)
        self.assertFalse(result[0])
        self.assertIn("projected portfolio", result[1])
        with self.assertRaises(ValueError):
            whole_share_size(equity=10000, risk_fraction=.01,
                             entry=100, stop=100, max_asset_fraction=.2,
                             max_position_value=1000)


class LegacyDBTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "legacy.sqlite"
        self.mod = load_source("core/shnifter_data_manager.py",
                               strip_global_manager=True)
        self.manager = self.mod.ShnifterDataManager(str(self.path))

    def test_new_trade_stored_with_id_and_exact_closure(self):
        manager = self.manager
        manager.add_trade("AAPL", 100, 2, stop_loss=90)
        manager.add_trade("AAPL", 110, 1, stop_loss=90)
        ids = [t.trade_id for t in manager.portfolio.get_open_trades()]
        self.assertEqual(len(set(ids)), 2)
        with self.assertRaisesRegex(ValueError, "trade_id is required"):
            manager.close_trade("AAPL", 120)
        manager.close_trade("AAPL", 120, trade_id=ids[0])
        with sqlite3.connect(self.path) as conn:
            status = dict(conn.execute("SELECT id,status FROM trades"))
        self.assertEqual(status[ids[0]], "closed")
        self.assertEqual(status[ids[1]], "open")
        self.assertEqual(len(manager.get_trade_history()), 1)
        reloaded = self.mod.ShnifterDataManager(str(self.path))
        self.assertEqual(len(reloaded.portfolio.get_open_trades()), 1)
        self.assertEqual(reloaded.portfolio.get_open_trades()[0].trade_id, ids[1])
        self.assertEqual(len(reloaded.portfolio.closed_trades), 1)
        self.assertGreater(reloaded.portfolio.balance, 100000)

    def test_failed_insert_never_creates_ghost_open_trade(self):
        manager = self.manager
        with patch.object(manager, "_save_trade",
                          side_effect=sqlite3.OperationalError("disk full")):
            with self.assertRaises(sqlite3.OperationalError):
                manager.add_trade("AAPL", 100, 1)
        self.assertEqual(manager.portfolio.get_open_trades(), [])

    def test_failed_closure_does_not_mutate_memory(self):
        manager = self.manager
        manager.add_trade("AAPL", 100, 1)
        trade = manager.portfolio.get_open_trades()[0]
        with patch.object(manager, "_update_trade_in_db",
                          side_effect=sqlite3.OperationalError("read-only DB")):
            with self.assertRaises(sqlite3.OperationalError):
                manager.close_trade("AAPL", 120, trade_id=trade.trade_id)
        self.assertEqual(trade.status, "open")
        with sqlite3.connect(self.path) as conn:
            self.assertEqual(conn.execute("SELECT status FROM trades").fetchone()[0],
                             "open")

    def test_older_open_trades_are_not_hidden_by_latest_100(self):
        manager = self.manager
        manager.add_trade("AAPL", 100, 1)
        oldest_id = manager.portfolio.get_open_trades()[0].trade_id
        with sqlite3.connect(self.path) as conn:
            conn.executemany(
                "INSERT INTO trades(ticker,entry_price,size,direction,status,pnl) "
                "VALUES('MSFT',100,1,'long','closed',?)",
                [(0.0,) for _ in range(120)]
            )
        newer = self.mod.ShnifterDataManager(str(self.path))
        self.assertEqual(newer.portfolio.get_open_trades()[0].trade_id, oldest_id)

    def test_profit_factor_uses_gross_wins_and_losses(self):
        manager = self.manager
        for index, (entry, exit_price) in enumerate(
                ((100, 200), (100, 200), (100, 50))):
            manager.add_trade("AAPL", entry, 1, stop_loss=40)
            trade_id = manager.portfolio.get_open_trades()[0].trade_id
            manager.close_trade("AAPL", exit_price, trade_id=trade_id)
        stats = manager.get_trading_stats()
        self.assertAlmostEqual(stats["profit_factor"], 4)
        self.assertIsNone(stats["sharpe_ratio"])

    def test_absent_data_objects_return_empty_dict(self):
        self.assertEqual(self.manager.get_model_performance("missing"), {})
        self.assertEqual(self.manager.get_market_data("missing"), {})


if __name__ == "__main__":
    unittest.main()
