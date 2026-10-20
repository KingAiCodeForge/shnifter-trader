"""Real local stdio protocol smoke; no market tool or brokerage is invoked."""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path


@unittest.skipUnless(importlib.util.find_spec("mcp"), "optional MCP dependency is unavailable")
class StdioSmokeTests(unittest.TestCase):
    def test_real_stdio_initialization_allowlist_and_research_capabilities(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        async def check(cwd):
            module = Path(__file__).resolve().parents[1] / "shnifter_agent_mcp.py"
            parameters = StdioServerParameters(command=sys.executable,
                args=[str(module)], cwd=cwd, env=dict(os.environ))
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write,
                        read_timeout_seconds=timedelta(seconds=15)) as session:
                    initialized = await session.initialize()
                    self.assertTrue(initialized.serverInfo.name)
                    tools = await session.list_tools()
                    self.assertEqual({tool.name for tool in tools.tools}, {
                        "shnifter_capabilities", "shnifter_market_historical",
                        "shnifter_analysis_signals", "shnifter_backtest_replay"})
                    response = await session.call_tool("shnifter_capabilities", {})
                    self.assertFalse(response.isError)
                    payload = json.loads(next(block.text for block in response.content
                                              if hasattr(block, "text")))
                    self.assertEqual(len(payload["actions"]), 4)
                    self.assertTrue(all("order" not in action["name"] for action in payload["actions"]))
                    denied = await session.call_tool("place_order", {"side": "BUY"})
                    self.assertTrue(denied.isError)

        with tempfile.TemporaryDirectory(prefix="mcp arbitrary cwd ") as cwd:
            asyncio.run(asyncio.wait_for(check(cwd), timeout=30))


if __name__ == "__main__":
    unittest.main()
