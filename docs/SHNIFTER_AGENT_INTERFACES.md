# Shnifter Agent Interfaces — staged integration

2026-10-17. Implemented on branch `review/analysis-core-refactor-20261017`
stacked on `review/deterministic-replay-20261017`.

## Why CLI + MCP + HTTP?

One headless service should serve four clients:
- User GUI (PySide6): existing interface and charts.
- CLI: Codex, Claude Code, scripts and scheduled offline jobs.
- MCP stdio: Claude Desktop/Code and other local MCP hosts.
- FastAPI HTTP: dashboards and permitted machine integrations.

Never duplicate signal/risk/execution logic in each adapter. Current action
registry is restricted to **read-only** research, not paper account writes,
trade signals with execution authority, or broker order submissions.

## Working CLI calls

```sh
python shnifter_cli.py --help
python shnifter_cli.py actions list
python shnifter_cli.py analysis signals --csv prices.csv --ticker AAPL --fast 20 --slow 50
python shnifter_cli.py analysis signals --csv prices.csv --ticker AAPL --no-ml --output signals.json
python shnifter_cli.py backtest run --csv prices.csv --ticker AAPL --fast 20 --slow 50 --fee-bps 10 --slippage-bps 5
python shnifter_cli.py market historical --ticker AAPL --start 2026-01-01 --end 2026-10-01
```

CSV must contain date,open,high,low,close,volume in chronological order.
Dates are strict calendar days; original raw prices may differ from research
split-adjusted data. The CLI produces structured JSON; writing an existing
file requires `--overwrite`. Research return value `SELL` does not create
a short or broker order. `probability_up_uncalibrated` is not a probability
of profit or allocation instruction.

## Local HTTP API

```sh
python -m uvicorn shnifter_agent_api:app --host 127.0.0.1 --port 8766
```

`GET /v1/actions`, `POST /v1/actions/market.historical`, and
`POST /v1/actions/analysis.signals` use JSON.
Example body:

```json
{"params":{"ticker":"AAPL","rows":[{"date":"2026-01-02","open":100,"high":102,"low":99,"close":101,"volume":3000}]}}
```

That body illustrates schema only; the analysis requires adequate history.
No file paths or broker keys are accepted through the API.

Without `SHNIFTER_READONLY_API_KEY`, only requests whose peer address is
loopback are authorised. With it set, clients must supply `x-api-key`.
This is a **development** boundary; any external deployment additionally
requires TLS, proper reverse-proxy authentication, least-privilege access and
request/rate limits. Do not expose the API over open Internet or put keys in
repository files.

## Local MCP server

Current Python SDK v2 uses `MCPServer` from `mcp.server`:

```sh
python -m pip install 'mcp>=2,<3'
python shnifter_agent_mcp.py
```

The command expects a compatible MCP host to supply protocol messages over
stdio. Configure Claude Desktop/Codex to launch the project's Python
interpreter with this file as the argument. MCP tools include
`shnifter_capabilities`, `shnifter_market_historical`,
`shnifter_analysis_signals` and `shnifter_backtest_replay`.
`shnifter_market_historical` performs a read-only network fetch through
ShnifterBB/yfinance; all other registered tools operate on supplied data.
None exposes a broker.

Official SDK: https://py.sdk.modelcontextprotocol.io/
The v2 SDK was used as the reference, but a complete MCP host handshake and
SDK runtime test has **not** yet been performed on this review branch.

## ML and GUI changes

- `evaluate_signals` no longer fabricates a last-row next-day negative
  training label, uses lagged price returns/features and a chronological
  validation slice with a one-row gap.
- The holdout score is measured, not randomly produced. Validation samples
  are small and repeated hyperparameter tuning will invalidate the holdout.
- GUI adapters call the same analysis core; normal GUI analysis no longer
  generates implied paper trades or invented model-performance records.
- Legacy dual-LLM GUI flow may still block the UI while Ollama responds;
  asynchronous UI-thread separation remains a follow-up.

## Next integration increments

1. Verify full PySide6 GUI smoke run and wheel install on the target machine.
2. Verify MCP handshake in a real Claude/Codex client; pin SDK after testing.
3. Add permissions and execution ledger for **paper-only** order actions.
4. Add an optional LLM research service with cited sources, an explicit
   insufficient-evidence answer and cost limits. It must never invoke a
   broker or modify risk policy.
5. Add broker adapter only after idempotent fills, restart reconciliation,
   account snapshots, permissions and kill-switch tests are complete.

## Verified local test scope

42 Python 3.13 offline unittest cases passed in a focused working folder
(earlier CLI/history, replay, new action adapters and risk sizing). The
MCP adapter's registered tools were checked with an injected fake SDK;
actual MCP v2 hosting/handshake remains unverified. The tests use synthetic
bars and mock network fetching; they do not demonstrate market alpha.
