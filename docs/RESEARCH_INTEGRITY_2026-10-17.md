# Research integrity repairs — 17 October 2026

Base: `3ce098417ce37d5353e79594022b9580990af31f` (draft PR #9).
Branch: `review/research-integrity-20261017`.
Scope: offline research correctness, local report-file safety, and CLI automation.
No broker integration, live permission, external data purchase or default-branch change.

## Completed

### Correct benchmark drawdown and execution arithmetic

The previous benchmark initialised its equity peak to **cash remaining after
buying shares**, rather than the full initial portfolio equity. Reproduction:
$10,000 initial cash, 20 shares bought at $100, then the first close at $80.
That is a 4% portfolio loss, but the previous benchmark reported 0% drawdown.
The fixed benchmark reports **-4% return and 4% maximum drawdown**.

Benchmark entry prices and commissions now use the existing replay engine's
cent rounding rather than a different unrounded model. Both ordinary and
cost-stressed buy-and-hold results are reported. Neither sells a still-open
position merely to improve a metric; final holdings are marked to the last
close and remain subject to unmodelled exit costs.

The evaluation engine is explicitly versioned `shnifter.oos-fold-evaluator.v2`.
Previous results and evaluation IDs must not silently be treated as v2 results.
Policy money fields normalise finite ordinary numbers/decimal strings to
Decimal. Booleans, NaN, Infinity and duplicate direct-API candidate pairs are
rejected. Candidate selection still uses earlier validation data only.

### Prevent source-data destruction and partial JSON files

Reproduced: `analysis signals --csv prices.csv --output prices.csv --overwrite`
returned success after replacing its own source CSV with JSON.

`analysis signals`, `backtest run`, and `research gate` now use the shared
`shnifter_safe_output.py` helper. It protects direct source paths and hard-link
aliases, refuses output symlinks, requires an existing parent directory, and
checks overwrite permission before expensive processing. Backtest reports
also cannot overwrite the requested experiment database or its WAL/SHM paths.

Reports are written into a temporary file in the destination directory, flushed
and fsynced before publication. Normal writes publish with a no-clobber hard
link; explicit overwrites use replacement. Injected fsync/publish errors leave
old reports intact. A concurrently created destination is not overwritten when
`--overwrite` is absent. Temporary files are removed after ordinary failures.

Limits: trusted local directories only. This is not a security sandbox against
an attacker replacing parent directories concurrently. Network filesystems,
Windows runtime behaviour and sudden-power-loss recovery were not tested.
Unsupported hard links fail closed. Directory fsync is best effort. A committed
SQLite experiment and a JSON report are separate transactions: a later JSON
write failure does not roll back an already recorded experiment.

### Machine-readable screening controls

```bash
python shnifter_cli.py research gate --csv prices.csv --ticker AAPL --summary-only --fail-on-rejection
```

`--summary-only` removes per-fold detail from JSON but retains the identical
evaluation ID, policy/data hashes, aggregate metrics, rejection reasons and
limitations. It does not change the strategy or relax acceptance conditions.

`--fail-on-rejection` makes a successfully completed but rejected screening
return exit **3**, while preserving its JSON report. Without this flag, completed
screenings retain the previous exit-0 behaviour.

| Exit | Meaning |
| --- | --- |
| 0 | Operation completed; inspect `paper_research_candidate` |
| 1 | Data, calculation or output error |
| 2 | Invalid CLI syntax/option combination |
| 3 | Screening completed but rejected; only with `--fail-on-rejection` |

Neither exit 0 nor a positive research screening authorises any trade.
`live_authorized` remains false in every report and output-file receipt.

## Validation actually run

One local invocation: `python -m pytest -q tests --disable-warnings`.
**96 tests and 78 subtests passed**, including **30 new test methods**.
The new tests cover initial loss, fee rounding, stressed benchmark, typed policy
inputs, duplicate candidates, input/hard-link/symlink protection, injected disk
and publication failures, competing output creation, all three CSV command
paths, compact reports and actual subprocess exit codes/help.

The workspace is an assembled **source subset**, not a full repository clone.
Git clone failed because the container could not resolve github.com. Current
connector source and available mounted source archives supplied the subset;
Git blob hashes were checked for the relevant base source, and final changed
source hashes are recorded in `RESEARCH_INTEGRITY_TEST_RECEIPT.json`.

No complete installed wheel, GUI, actual MCP host, authenticated data feed,
paper brokerage account, legacy risk-manager suite, or economic-profitability
experiment was run. Prices in tests are synthetic. Passing tests demonstrate
these software contracts, not a trading edge.

## Remaining TODOs

- Extend safe report output to legacy GUI exports and market-history CLI output.
- Test installed package and the integrated branches on Windows and a real MCP host.
- Replace immediate-fill paper simulation with acknowledged/partial/cancel-pending
  order states and reconcilable execution IDs.
- Record failed research attempts and code/data versions in a trial registry;
  independently seal final evaluation data.
- Use verified point-in-time data and measured all-in broker costs before making
  any profitability claim. No live-account activation is part of this branch.

## Primary technical references

Python filesystem operations: https://docs.python.org/3/library/os.html

Chronological split rationale: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
