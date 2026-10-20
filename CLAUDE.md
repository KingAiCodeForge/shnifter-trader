# Claude guidance — Shnifter Trader

Read [AGENTS.md](AGENTS.md) for architecture and safety rules.
Use the existing `shnifter_cli.py` commands for deterministic research.
Use `shnifter_agent_mcp.py` with MCP Python SDK v2 for approved read-only tools.
Do not change a research signal into an order, bypass risk limits or enable
live brokerage routing. Add future commands to the shared service registry,
with tests, not as duplicate business logic in separate interfaces.
