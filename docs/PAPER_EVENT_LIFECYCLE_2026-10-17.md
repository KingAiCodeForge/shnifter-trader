# Paper order lifecycle and exact-source focused tests

Base commit: `4dd97af0ca226dc1318524f25ea0aa2852b891cf` (draft PR #10).
Review branch: `review/paper-event-lifecycle-20261017`.

## Implemented, not a live broker integration

`shnifter_order_events.py` is a new, separate, event-sourced **paper account**.
It does not replace, overwrite, migrate or claim compatibility with the old
`paper` ledger. Use a NEW database path. No network, broker SDK, credentials,
LLM, external orders or live-account permissions exist in this module.

The older `paper order` command still means immediate whole fills. The new
`paper-events` commands instead distinguish an intent, simulated transmission,
acknowledgement, partial executions, cancellation and reconciliation.

## States, identity and reservations

States: NEW, PENDING_SUBMIT, ACKNOWLEDGED, PARTIAL, CANCEL_PENDING, CANCELLED,
FILLED, REJECTED, UNKNOWN. Each order has a stable order ID, each request a
stable event ID and each simulated execution a stable execution ID.

Repeating the same event ID and content does not create another event. A
second delivery of an already-known execution ID does not book it twice.
Conflicting execution details are saved to quarantine and block new intentions.
An event ID reused with changed content is rejected rather than overwritten.

Buying reserves the maximum remaining limit-price notional plus the unused
commission budget. Selling reserves existing long shares. Pending orders,
UNKNOWN outcomes, and cancelled-but-not-reconciled orders keep reservations.
Concurrent commands cannot spend the same available cash or reserve the same
long shares twice. Order and aggregate **cost** caps are set at initialisation.
These are not mark-to-market equity, volatility, leverage or drawdown controls.

A cancellation request is not a fill and does not release sent-order reserves.
A cancellation acknowledgement alone still does not release those reserves.
A delayed execution can be accounted for while cancellation is pending or
acknowledged. Explicit reconciliation must match the complete local execution
ID set and filled quantity before unfilled reservations are released.

A new execution contradicting an already-reconciled terminal state is retained
as quarantine evidence; cash is not guessed or silently rebalanced. The account
then requires investigation. No automatic quarantine-clear/reset path exists.
Status displays `ok=false` and `requires_reconciliation=true`. This reflects
uncertain accounting, NOT a claim that the external fill could safely be ignored.
There is no external broker here: every delivered execution is a simulation input.

UNKNOWN transmission cannot be retransmitted. A later cancellation does not
clear uncertainty; only matching reconciliation or complete recorded fills can
resolve that order. Delayed acknowledgements cannot regress completed or partial
states. A persistent manual halt blocks entries while allowing a bounded sale
of already-held, unreserved shares. It never resets on a clock/date change.

## Exact arithmetic and replay

All monetary accounting is in integer cents; fractional-cent inputs are rejected.
This release supports whole-share, long-only, equity-symbol LIMIT orders in one
currency only. Commission budgets and each fill's simulated commission are
explicit. Buy fills above the limit, sell fills below it, excess fees and overfills
are quarantined. No fill is generated automatically from a BUY/SELL analysis.

After every valid event the reducer checks:

    cash + remaining position cost = initial cash + realised P&L
    reserved cash <= cash
    reserved sell shares <= held shares

Position costs use deterministic integer average-cost allocation. That is a
simulation accounting choice, not a tax-lot or broker settlement implementation.
Cash and cost basis are not NAV; no real market price is inferred.

Only an append-only, versioned SQLite event stream is persisted. Every operation
reconstructs state from that stream. A new event is validated and inserted inside
one BEGIN IMMEDIATE transaction; financial state has no separate mutable cache.
Sequence numbers and chained hashes detect ordinary alteration. SQL triggers
block normal UPDATE/DELETE. These checks are NOT signatures and cannot protect
against a filesystem owner replacing the whole database and recomputing hashes.

The implementation deliberately favours simplicity over throughput: at most
10,000 events, with full replay for each transaction. It is not intended for
high-frequency execution or a large multi-account production database.

## CLI example — entirely simulated

Run each line from the review checkout, using a new database path:

```bash
python shnifter_cli.py paper-events init --db demo_events.sqlite
python shnifter_cli.py paper-events submit --db demo_events.sqlite --event-id intent1 --order-id o1 --ticker AAPL --side BUY --quantity 5 --limit-price 100 --fee-budget 1
python shnifter_cli.py paper-events transmit --db demo_events.sqlite --event-id sent1 --order-id o1
python shnifter_cli.py paper-events ack --db demo_events.sqlite --event-id ack1 --order-id o1
python shnifter_cli.py paper-events fill --db demo_events.sqlite --event-id fill1 --order-id o1 --execution-id exec1 --quantity 2 --price 99 --fee .30
python shnifter_cli.py paper-events cancel-request --db demo_events.sqlite --event-id cancel1 --order-id o1
python shnifter_cli.py paper-events cancel-ack --db demo_events.sqlite --event-id cancelled1 --order-id o1
python shnifter_cli.py paper-events reconcile --db demo_events.sqlite --event-id reconciled1 --order-id o1 --status CANCELLED --filled-quantity 2 --execution-ids exec1
python shnifter_cli.py paper-events status --db demo_events.sqlite
python shnifter_cli.py paper-events verify --db demo_events.sqlite
```

The example buys only the two explicitly simulated fills, not five shares.
Cash becomes 980,170 cents; held position cost is 19,830 cents. The 30,070-cent
remaining reservation is held after cancellation acknowledgement and released
only after matching reconciliation. The result stays `live_authorized=false`.

Other commands: `reject`, `unknown`, `halt`. All have `--help`. No `live`
command exists. CLI exit 0 means the local operation completed, not permission to
trade; exit 1 is invalid input/storage failure; exit 2 is argument usage error;
exit 3 means persisted/replayed quarantine evidence remains unresolved.

These are deliberately local file-writing actions, not new MCP/HTTP broker
capabilities. The existing read-only action registry remains unchanged.

## Test runner and scope

```bash
python tools/run_shnifter_focused_tests.py --suite focused --output-dir test-results-new --expected-manifest docs/PAPER_EVENT_SOURCES.json
```

The output directory must be NEW. The runner checks expected source hashes before
launch, records actual commands, package versions, log and JUnit results, then
checks sources again after execution. Missing selected tests, changed sources,
zero collected tests, failures, skips and timeout cannot be reported as PASS.
JUnit case counts can include subtests; separate pytest-reported method/subtest
counts are also recorded when available. Do not add these together as independent
full-application tests.

Suites are explicit: research, existing paper, new lifecycle and runner. This is
not the full repository suite. The full clone was blocked by GitHub DNS in the
working container. Existing source was assembled from mounted test kits and
commit-pinned connector reads, with relevant Git blob hashes checked. In
particular, the exact committed old paper ledger and its tests were recovered and
rerun, resolving the earlier older-snapshot test limitation for those files.

The new tests include forced process death before commit, failure after event
insertion, duplicate deliveries across restarts/processes, concurrent cash
reservation, cancellation/fill races, terminal contradictions, fee and limit
violations, hash corruption and actual CLI subprocess calls.

No full GUI, Windows runtime, installed distribution, real MCP host, quote feed,
IBKR/Alpaca account or profitability study was tested. Monetary prices are all
synthetic or manually supplied simulation values.

## Remaining work

- Broker-specific adapter and authenticated complete snapshots; source-specific
  ordering/correction rules, commissions arriving later, reconnect handling.
- Controlled quarantine recovery with compensating events, independently reviewed.
- Matching/latency/volume model, session calendars, FX, corporate actions, settlement,
  current quotes and NAV-based risk; these are not implied by persistent accounting.
- Strategy scheduler, health monitoring and production migration plan.
- Full checkout tests, install/GUI/MCP checks, and independent real-data research.

## Technical references

SQLite transactions and BEGIN IMMEDIATE:
https://www.sqlite.org/lang_transaction.html

IBKR's published order lifecycle documentation (historical reference; not an
adapter specification for this simulator):
https://interactivebrokers.github.io/tws-api/order_submission.html
