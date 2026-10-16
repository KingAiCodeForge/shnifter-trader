"""Optional local stdio MCP server; read-only Shnifter research tools.

Requires MCP Python SDK v2: pip install 'mcp>=2,<3'
Use Python interpreter of the Shnifter environment in Claude/Codex config.
Do not expose this stdio process to an untrusted host with file permissions.
"""
from __future__ import annotations

from typing import Any

from shnifter_actions import invoke_action


def build_server():
    # Optional dependency; CLI and REST API do not require the MCP SDK.
    from mcp.server import MCPServer

    server = MCPServer("Shnifter Research — read only")

    @server.tool()
    def shnifter_capabilities() -> dict[str, Any]:
        """Discover Shnifter's allowlisted research tools and safety restrictions."""
        return invoke_action("actions.list")

    @server.tool()
    def shnifter_analysis_signals(ticker: str, rows: list[dict[str, Any]],
                                  fast: int = 20, slow: int = 50,
                                  min_labeled: int = 80) -> dict[str, Any]:
        """Analyse completed OHLCV daily bars. Signals are NOT orders."""
        return invoke_action("analysis.signals", {
            "ticker": ticker, "rows": rows, "fast": fast, "slow": slow,
            "min_labeled": min_labeled,
        })

    @server.tool()
    def shnifter_backtest_replay(ticker: str, rows: list[dict[str, Any]],
                                 fast: int = 20, slow: int = 50,
                                 initial_cash: str = "10000", fee_bps: str = "10",
                                 slippage_bps: str = "5") -> dict[str, Any]:
        """Replay a long-only strategy; never places a real or simulated account order."""
        return invoke_action("backtest.replay", {
            "ticker": ticker, "rows": rows, "fast": fast, "slow": slow,
            "initial_cash": initial_cash, "fee_bps": fee_bps,
            "slippage_bps": slippage_bps,
        })

    return server


if __name__ == "__main__":
    build_server().run(transport="stdio")
