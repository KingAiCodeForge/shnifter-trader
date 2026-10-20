# Paper execution admission audit — 17 October 2026

Base: `d11172cfdd2875927179f69c505e270521e46492` (draft PR #11).
Branch: `review/paper-admission-safety-20261017`.
Scope: local paper-event code inspection, adversarial reproduction and tested fixes.
No broker account, quote feed, secret, real-money order, GitHub Actions or main merge.

## Confirmed defects and repairs

### 1. A staged order could bypass a later halt or reconciliation fault

Reproduced against the pinned v1 source: create a NEW BUY intention, activate
HALT, then TRANSMIT that already-staged intention. The order became
PENDING_SUBMIT even though manual_halt remained true. Equivalent staged
transmissions also succeeded during UNKNOWN, quarantine, and acknowledged but
unreconciled cancellation/rejection of another order.

The cause was validating these conditions at SUBMIT but not at TRANSMIT.
Both operations now use the same reconciliation predicate. TRANSMIT rechecks
account uncertainty and the manual entry halt inside the same SQLite write
transaction that records the state change. Cancelled/rejected sent orders that
have not reconciled now block new intentions consistently with status output.

This does not retroactively undo a transmission or ignore its later execution.
Fills from already-sent orders remain recordable during a halt. A verifiable
closing SELL can proceed during a manual entry halt, but not through unresolved
account uncertainty. Local cancellation of unsent intentions remains available.
A concurrent halt/transmit test verifies the committed ordering: transmission
can succeed only when it is recorded before the halt, never after it.

### 2. Reaching the event limit disabled safety operations

The previous MAX_EVENTS check rejected EVERY new event at the limit, including
HALT, FILL and CANCEL_REQUEST. Those paths were reproduced with the same branch
logic at a reduced test limit of three events; a full 10,000-event stress run
was not performed.

The limit now applies to new BUY intentions and staged BUY transmissions only.
Halts, known executions, cancellation, reconciliation and bounded closing sales
remain recordable beyond it. Replay can read the resulting longer stream.
Duplicate deliveries remain idempotent. Existing resource, accounting,
reconciliation and quarantine validations still apply; capacity is not an
excuse to bypass those controls.

This deliberately allows cleanup records to exceed the admission limit. It is
NOT an unbounded-throughput guarantee: full replay still grows with history,
disk exhaustion still matters, and the account should be retired after a
reconciled wind-down. Persisted snapshots and archival controls remain future
work. Do not deploy it as a high-frequency or large broker-account database.

### 3. Replay repeatedly deep-copied the entire growing account

Each saved event previously called the public pure reducer, cloning all orders,
positions and executions again. The loader now owns one private projection and
applies validated events to it directly. That object is not published unless
replay succeeds. New-event admission retains the pure copying interface, and
public reduce_event() still leaves the caller's input entirely independent.

Measured local microbenchmark: 501 valid synthetic events (250 intent/local-
cancellation pairs), five status/replay measurements per version. Median time
was 0.413100776 seconds before versus 0.014381352 seconds after (about 28.7x in
this specific fixture). The reconstructed state SHA256, orders and balances
matched. This is NOT whole-application, broker or market-latency performance.
Invariants and hash verification remain active; no checks were removed to
produce the improvement.

### 4. Malformed saved event envelopes could escape as raw TypeError

A deliberately malformed local fixture with canonical JSON null and a recomputed
content hash previously raised an unhandled TypeError during loading. The loader
now validates the envelope type, fields and size, verifies the sequence/hash,
and converts malformed state transitions to an IntegrityError identifying the
sequence. The CLI returns its normal structured failure rather than a traceback.
No financial state is guessed or partially published on this failure.

## Version and CLI implications

The reducer is now `shnifter.paper-events.v2`. The rules for valid historical
transitions have changed. Existing v1 databases are refused, not silently
reinterpreted or overwritten. No migration exists in this change. Preserve
old stores for review, and use a NEW path for fresh v2 simulations:

```bash
python shnifter_cli.py paper-events init --db paper_events_v2.sqlite
python shnifter_cli.py paper-events status --db paper_events_v2.sqlite
```

Status adds `entry_block_reasons`, `new_entries_allowed` and
`entry_admission_limit`. Reasons distinguish manual halt, unreconciled state
and capacity. This is an account-level admission summary, not an order-size,
quote-freshness or broker authorisation decision. `live_authorized` stays false.
All existing CLI actions remain available; MCP/HTTP write permissions do not
change. A duplicate TRANSMIT receipt only confirms an already-recorded event;
it is never a command to retransmit to a broker.

## Actual validation

The original assembled source subset first passed its 170 existing test methods
and 93 subtests. Additional regression cases then reproduced the faults before
changes. The final combined focused runner reports **197 methods and 99 subtests
passed**, including **27 new methods**; no errors, failures or skips.

```bash
python tools/run_shnifter_focused_tests.py --suite focused --output-dir results-new --expected-manifest docs/PAPER_ADMISSION_SOURCES.json
```

Source hashes are checked before and after the run. Changed runtime/test blobs
are matched to the files committed through GitHub. Full logs, JUnit, exact source
manifest and benchmark measurements accompany the downloadable source subset.
The previous source manifest is historical and intentionally does not match v2.

The full clone still failed because this container could not resolve GitHub.
The working directory was assembled from the mounted PR #11 test kit and checked
against pinned connector source. It is NOT a complete repository checkout.
No full GUI, Windows runtime, installed wheel, actual MCP host, legacy risk-
manager suite, real market dataset or brokerage account test was performed.
These software tests and synthetic timings do not demonstrate profitable alpha.

## Further finding — NOT fixed here

An event hash chain without a trusted external head cannot detect replacement
with an older valid prefix. A local rollback fixture deleted the last HALT event
(after deliberately dropping the append-only trigger). The remaining prefix
verified and reconstructed manual_halt=false. This represents privileged local
modification/backup rollback, not a remotely demonstrated exploit.

A future recovery design must compare a trusted external checkpoint or signed
snapshot/monotonic generation before accepting restored account state. Merely
hashing the same database again cannot prove it is the newest copy. Until then,
backup restoration needs deliberate verification; no automatic live restart.

Other remaining gaps: authenticated broker snapshots, timestamped quote-driven
matching, mark-to-market NAV and drawdown checks, late commissions/corrections,
corporate actions, controlled quarantine recovery and full application testing.

Technical reference: SQLite BEGIN IMMEDIATE and transaction semantics:
https://www.sqlite.org/lang_transaction.html
