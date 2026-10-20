# Paper database preservation and checkpoint limits

This is local software research and paper execution only. No brokerage account,
market matching, profitable strategy, live order or money operation is qualified.

## Version 1 is preserved; version 2 starts separately

`shnifter.paper-events.v2` has different admission/reducer rules. Reading a v1
database fails with an explicit message. There is no automatic migration,
renaming, deletion, overwrite, replay under different rules, or recovery of a
corrupted database. Keep the original database and all SQLite WAL/SHM sidecars.
Back up those files consistently using SQLite's backup facilities while the old
application is stopped or otherwise quiescent. Preserve an independently recorded
hash and retain the matching old software/ref for investigation.

Create a **new, unused path** for an independent v2 simulation:

```text
shnifter-trader paper-events init --db "research runs/paper-v2-new.sqlite"
shnifter-trader paper-events verify --db "research runs/paper-v2-new.sqlite"
```

The parent directory must already exist. `init` refuses an existing file even
when it is empty or contains a v1 database. This is a separate experiment, not a
migration of positions, balances, execution identities, uncertainty or HALT.
Do not carry over a cash number and call the prior account reconciled.

## What a hash chain can and cannot prove

The database sequence and hash chain detect ordinary changes inside the retained
event history. A privileged actor, old backup or copied file can replace the
database with an earlier **valid prefix**. A lost final HALT then disappears and
the remaining hashes still verify. An adjacent checkpoint replaced with the same
backup does not solve this. A chain cannot prove that its newest retained event
is the newest event that ever existed.

The new optional detached checkpoint records reducer version, event count and
head hash. A caller may supply it from independently trusted storage:

```text
shnifter-trader paper-events checkpoint --db "research runs/paper-v2-new.sqlite" --output "independent anchors/account-0001.json"
shnifter-trader paper-events verify --db "research runs/paper-v2-new.sqlite" --checkpoint "independent anchors/account-0001.json"
```

Export never overwrites an existing anchor, the database, its sidecars, or the
input checkpoint. It does **not** establish independent trust merely by writing
JSON. Preserve the anchor somewhere whose trust and rollback policy are
independent of the simulation database. Keep monotonically versioned anchors;
do not silently select the newest filename from an untrusted directory.

All mutation commands accept `--checkpoint`. A shorter database or a different
hash at the anchored sequence fails before an event is inserted. A valid extension
of that exact anchored prefix is accepted. Tests reproduce a lost HALT and show
that a checkpoint at or after it rejects the rollback without altering either
file. Anchors are validated and copied before use.

## Remaining freshness hold

An old trusted anchor cannot detect rollback of events **after that anchor**.
Replacing both database and anchor remains undetectable without an independent
authority that retains a later monotonic state. Exporting an anchor after SQL
COMMIT creates a crash window; this implementation does not claim an atomic
transaction across independent stores. No external monotonic/checkpoint service,
hardware counter, operator restore ceremony or independently durable HALT latch
has been implemented or tested.

Receipts always state `freshness_proven=false`. `checkpoint_verified=true` means
only that the supplied anchor exists in the retained chain; the anchor count and
events after it are displayed. Without an anchor, `checkpoint_verified=false`.
These explicit local simulations remain available without an anchor for research
compatibility. **Never use either field as permission for live execution or
automatic account recovery.** A stale/missing anchor is an unresolved freshness
hold, even when a normal hash check passes.

The v1-preservation and detached-checkpoint regressions use temporary synthetic
databases. They demonstrate these limited software properties, not power-loss,
hostile-filesystem, broker recovery or external trust infrastructure validation.
