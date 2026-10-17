# Shnifter Experiment Registry — October 17, 2026

## What is implemented

Shnifter can now **explicitly** save a deterministic backtest run to a
separate, locally persisted SQLite research database. Ordinary historical
queries, signal analysis and backtests remain read-only unless recording is
requested. The registry has **no brokerage, orders, portfolio writer, cloud,
LLM or GUI dependency**.

A saved experiment includes:
- Full historical daily OHLCV bars used by the run (not just a filename)
- The complete original replay JSON (signals, fills, equity curve and P&L)
- Strategy engine/version, ticker and exact parameter configuration
- Bar count, replay run ID and ISO UTC record time
- SHA256 digests of canonical dataset and report JSON
- A content-derived, stable experiment ID
- A **user-declared, unverified** data source description

Before writing, Shnifter recomputes the original backtest from its bars and
settings and refuses reports with invented or altered output. Read-time
verification checks content hashes, metadata and replays the calculation again.

## CLI usage

Use Python 3.13 from a checkout of the stacked review branches with the
necessary local dependencies installed:

~~~bash
python shnifter_cli.py backtest run \
  --csv historical_daily.csv --ticker AAPL \
  --fast 20 --slow 50 \
  --fee-bps 10 --slippage-bps 5 \
  --registry-db research_experiments.sqlite \
  --declared-source "user-supplied OHLCV, not independently verified"

python shnifter_cli.py experiments list \
  --registry-db research_experiments.sqlite --limit 20

python shnifter_cli.py experiments verify \
  --registry-db research_experiments.sqlite \
  --id YOUR_64_CHARACTER_SHA256_EXPERIMENT_ID
~~~

Use Windows CMD on one line, or PowerShell line continuation instead of
POSIX backslashes. The parent directory of the SQLite destination must
already exist. The path `shnifter_trading.db` is explicitly prohibited to
prevent accidental mutation of the existing simulated-trading ledger.

The CLI backtest still prints the original replay JSON to stdout. Registry
recording emits the saved experiment ID to stderr, preserving machine-readable
stdout. Recording the identical bars/report/source repeatedly is idempotent.
A different dataset, settings, or declared source generates a different ID.

## SQLite behaviour and boundaries

- Local-only; SQLite transactions; WAL and FULL synchronous mode for writes.
- Normal SQL UPDATE or DELETE on experiment rows is blocked by triggers.
- Reading/verification opens the database read-only and never creates one.
- Passing an existing, non-Shnifter SQLite database fails rather than
  silently appending foreign tables.
- Report-output file collisions are checked *before* creating a registry.
- A declared source label is **not** authenticated. It does not prove access
  to point-in-time prices, licensed quotes, corporate action adjustments,
  complete symbols, broker fills, or trading profitability.
- SQLite row-level triggers and SHA256 checks **do not make the database
  tamper-proof** against someone who can delete, replace, or rewrite the
  SQLite file and its triggers. External signing/backup requires a separate
  design.
- The replay remains single-symbol, long-only, daily OHLCV. It is not
  broker-paper order matching or a production live execution ledger.
- Recording is intentionally NOT exposed as an unauthenticated MCP/REST
  action. AI agents can invoke the local CLI if their host has local
  filesystem permissions, so only grant those permissions deliberately.

## How to test

~~~bash
python -m unittest discover -s tests -p 'test_shnifter_experiments.py' -v
python -m unittest discover -s tests -p 'test_shnifter*.py' -v
~~~

Tests use synthetic bars only. They cover record/read/verify, idempotency,
tampering, conflicting foreign databases, output collisions and CLI roundtrips.

## Remaining gaps

Build a persistent **trial registry** with failed attempts and all parameter
sweeps, not merely successful completed replays; split IDs for train,
validation and sealed holdout; point-in-time provenance with source publication
and acquisition times; cost-model versions; benchmarks and model-code hashes;
and benchmark-relative, uncertainty-aware evaluation. No new strategy should
be promoted to real-money execution based solely on a recorded backtest.
