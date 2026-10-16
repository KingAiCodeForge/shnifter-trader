# Shnifter Trader — incremental CLI action plan

Scope: KingAiCodeForge/shnifter-trader.
Baseline: main at 10c3eb7f3a837c9119012974d6fde9c634b25cff (2026-03-16).
Each action gets a parser, validation, a headless backend, machine-readable
output, offline regression tests and a reviewable GitHub commit. Do not
silently expose GUI callbacks as CLI commands.

## Action register

| Priority | Action | Current disposition |
| --- | --- | --- |
| 1 | market historical | **Implemented on review branch**: read-only, yfinance via ShnifterBB, JSON/CSV, date/symbol validation, tests |
| 2 | market news | **Not implemented**: validate upstream article schemas, published time and source URLs; no fabricated news |
| 3 | analysis signals | **Not implemented**: extract GUI-bound trend/ML/sentiment methods into one pure headless service; separate evidence from decisions |
| 4 | backtest run | **Implemented in review branch**: GUI/CLI use deterministic next-open daily SMA replay with costs, audit trail and risk halt; still needs real-market smoke testing |
| 5 | paper ledger | **Blocked**: migrate SQLite safely; durable IDs for signals, orders, executions and trades; close by trade ID |
| 6 | risk check | **Blocked**: deterministic exposure/position/drawdown/stale-data/duplicate checks independent of AI |
| 7 | paper cycle | **Blocked**: recoverable scheduled scan -> signal -> risk -> simulated fill -> ledger -> report; default dry-run |
| 8 | research explain | **Blocked**: optional bounded LLM research with timestamped citations and insufficient-evidence result |
| 9 | paper status / paper report | **Blocked**: real ledger-backed balances and measured model metrics only |
| 10 | paper scheduler | **Blocked**: restart/idempotency tests, failure policy, operator pause/stop |

Avoid adding buy/sell/broker/live-order CLI verbs before the ledger and risk
engine are validated. Proposed action names are a roadmap, not commands
that currently exist.

## Existing source risks that must not be disguised by the CLI

- Multi_Model_Trading_Bot.py: normal analysis result lacks confidence;
  the GUI falls back to 0.5 while the simulated-trade path requires >0.6.
  Decide whether to emit evidence-based confidence or remove the gate; do not
  arbitrarily raise confidence.
- Multi_Model_Trading_Bot.py: BacktestWorker previously generated random
  P&L/win-rate/trade metrics; review branch replaces this with Shnifter replay.
  This does not validate that the strategy makes money.
- Multi_Model_Trading_Bot.py: GUI model-performance values are derived
  from confidence rather than measured out-of-sample outcomes.
- core/shnifter_data_manager.py: review SQL writes/updates and reconciliation
  between in-memory positions and SQLite before any autonomous cycle.
- shnifterBB/shnifter_bb.py: only the yfinance provider is instantiated.
  Other provider names in GUI controls are not evidence of backend support.
- setup.py: the previous console script targeted an absent
  Multi_Model_Trading_Bot.main. First CLI slice corrects this, retaining
  the existing GUI file as a direct Python entry point.

## Acceptance criteria per action

1. --help works without importing Qt, Ollama, network clients or broker SDKs.
2. Strict parser semantics: documented types, bounds, defaults, exit codes.
3. Structured JSON for automation; CSV only where representation is meaningful.
4. Deterministic offline tests including invalid input, empty results, retries
   or failures, and schema incompatibilities as applicable.
5. No invented quotes, confidence percentages, returns, fill prices or P&L.
6. External effects explicitly gated and idempotent; no live order routes.
7. Verify only real behaviour. A passing unit test with synthetic data does
   not prove connection reliability, historical alpha, or GUI integration.
8. Keep changes off main pending review, and avoid GitHub Actions.

## Next engineering target

After the historical read and deterministic replay actions: repair the
**paper-only** ledger and position identifiers. Introduce a separately tested
SQLite store with atomic idempotent signals/fills and failure-safe risk gates.
Then wire scheduled autonomous paper cycles and optional LLM research.
Do not call a historical backtest a production-ready automated trader.
Profitability is an empirical result, never a feature assertion.
