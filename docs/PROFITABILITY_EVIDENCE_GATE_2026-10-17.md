# Shnifter — Evidence Before Capital

Research review dated 17 October 2026. This branch is **paper/research-only**, with no live order connectivity. No strategy currently demonstrates verified net-profitable live trading.

## Work combined on this review branch

- Earlier legacy risk/accounting repairs (draft PR #8 and its ancestors).
- Deterministic content-addressed SQLite experiment registry (PR #5).
- Fail-closed portfolio risk helper (PR #6).
- Algorithm literature and research notes (PR #3).
- Chronological three-fold out-of-sample evaluator, CLI action, 13 offline unit tests.
- Isolated paper-only order/accounting modules and existing offline tests from review/paper-ledger-20261017.
- MCP/HTTP agent-accessible actions remain read-only; no broker order permission was introduced.

## New CLI

Run from the source checkout:

    python shnifter_cli.py research gate --csv historical_daily.csv --ticker AAPL --folds 3 --validation-bars 80 --test-bars 80 --min-prior-bars 150 --candidates 5:20,10:30,20:50,20:100 --fee-bps 10 --slippage-bps 5 --stress-multiplier 2 --max-position-pct 0.20 --output oos_report.json

An input file needs chronological daily date,open,high,low,close,volume columns. Use --overwrite explicitly to replace the report file. The source and point-in-time availability of user-supplied prices are **not verified** by the CLI.

Other available commands include actions list, experiments list/verify, backtest run, paper init/status/order/halt. The paper commands use an isolated SQLite simulation, not a broker; they have no actual quote feed or reconciliation. Do not expose simulated order commands as public MCP actions.

## Screening design

1. Require enough early bars to warm rolling indicators; reject duplicate/unordered/nonfinite OHLCV.
2. For each fold, use historical data preceding an 80-bar validation period only for warming the indicators.
3. Choose from a predeclared moving-average grid using solely the validation net-return, drawdown and fill-count score. Later test prices do not select the candidate.
4. On later test bars, simulate next-open fills, stop/target exits, transaction costs, adverse slippage, whole shares, entry allocation and a drawdown halt.
5. Benchmark against same-allocation buy-and-hold plus cash. Repeat selected candidate with higher costs.
6. Log all validation candidates, selected windows, per-fold test results, undefined profit factors as null, unannualised per-bar mean/std ratio, and data/policy SHA256 digests.
7. A candidate may be flagged for **further paper research** only. Every result always reports live_authorized=false, even when synthetic performance is positive.

Earlier test folds can appear in later folds' validation history because they would already be known at the later date. Running multiple subsequent searches against displayed holdout results invalidates independence; truly sealed evaluation needs a separate dataset owner and evaluator.

## What is still required for live trading

- Verified point-in-time, legally obtained price/news data with market calendars, dividend/split handling, FX and fresh quotes.
- Durable broker order and execution identifiers, partial fills, cancellation races, exchange halts, unknown transmission states, recovery and reconciliation to IBKR's authoritative balances.
- Independent runtime permission gates and risk controls using measured equity, buying power, outstanding orders, real fees and downside scenarios.
- Broker-paper forward tests with documented failure/restart experiments; multiple instrument, market-regime and cost-sensitive out-of-sample studies against realistic benchmarks.
- Installed-wheel, GUI and MCP host integration tests; code licence/provenance and public tracked database review.

## Test evidence

The exact new OOS module, research CLI and dedicated tests matched the committed GitHub source by source length and FNV32 checksum. Thirteen focused OOS synthetic-data tests passed. A locally assembled partial workspace passed 89 older and new tests across research, registry, agent, risk and paper modules. The local paper ledger was an earlier 17,128-character revision, while GitHub's current paper-ledger branch has 18,387 characters; therefore 89 tests do NOT establish exact full-branch parity. No live market data, broker account, complete GUI or installed-package test has passed in this change.

Paper simulation can be made reliable; profitability cannot be guaranteed by software changes alone.

**Go/no-go today: NO-GO for autonomous live capital.**
