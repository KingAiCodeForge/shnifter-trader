# Public Shnifter integration qualification - 20 October 2026

This candidate reconciles the PR #1 -> #2 -> #4 -> #7 -> #8 -> #9 -> #10 ->
#11 -> #12 spine and preserves the distinct research, experiment-registry,
risk-helper and paper-ledger side histories. Three missing experiment-registry
documentation sections were recovered verbatim. No original ref or prototype
was deleted or rewritten. `SOURCE_REFS_2026-10-20.json` and
`BRANCH_COVERAGE_2026-10-20.md` record exact originals and content coverage.

## Result and actual evidence

- **279 test methods and 174 subtests passed** in one combined Windows source
  run: 453 JUnit cases, zero failures/errors/skips, 13 deprecation warnings.
  This runs all 23 top-level `tests/test_shnifter*.py` modules, including legacy
  simulations, isolated risk/accounting tests, the Qt widget, read-only HTTP
  adapter and actual local MCP stdio initialization/tool calls. Source hashes
  were unchanged before/after. The source test receipt lists exact files,
  package versions and commands. Subtests are not additional independent methods.
- **14 installed-package checks passed** in a new base virtual environment,
  invoked from an unrelated directory containing spaces. These cover the entry
  point, missing optional dependencies, analysis/replay with synthetic CSVs,
  invalid/missing inputs, no-clobber input preservation, explicit new v2 paper
  database, HALT, checkpoint export/verification and blocked BUY admission.
  `pip check` passed. Installed dependency versions and tested wheel SHA256 are
  recorded in `INSTALLED_PACKAGE_TEST_RECEIPT_2026-10-20.json`.
- The source GUI import smoke disabled network connections; Qt table and
  Windows launcher checks passed. These are limited smoke/regression checks,
  not complete GUI workflow validation. No market or model request was required.
- Wheel/sdist contents and current-source byte parity are enumerated in
  `PACKAGE_ASSET_AUDIT_2026-10-20.json`. No database, credential/config inventory,
  pyc, log, GUI/prototype or copied-framework file is an eligible asset member.

The first fresh Windows runs found real issues that the earlier assembled
subsets could not expose: legacy SQLite contexts did not close their handles,
the isolated test loader broke postponed dataclass annotations on Python 3.13,
Qt tests lacked QApplication, and table loading implicitly started an LLM worker
which could abort the process. Those are repaired; automatic table analysis is
now opt-in. An additional legacy in-memory simulator regression closes only the
exact trade record and rejects repeated/foreign closures. That prototype remains
separate from the event-sourced account.

Setup and launch scripts resolve their own quoted directory, preserve existing
environments/prototypes and propagate failure. GUI runtime state uses a user data
directory or explicit absolute `SHNIFTER_DATA_DIR`; a hard-coded model location
became explicit configuration. Known GUI/CLI exports now publish complete output
without silently replacing existing files. Original tracked local-state files
were untracked without deleting their bytes; hashes are recorded without data.

## Database and freshness boundary

Version 1 event databases are preserved unchanged and rejected with a clear
instruction to create a separate unused v2 path. No data migration, renaming or
balance carryover is claimed. Detached checkpoints can reject rollback through
their trusted count/head hash, including loss of an anchored HALT. They cannot
detect loss after a stale checkpoint or replacement of both files. All receipts
retain `freshness_proven=false` and `live_authorized=false`. See
`PAPER_CHECKPOINT_AND_V2_2026-10-20.md` for the exact restoration/trust limits.

## Release holds

Package version `0.2.0a1` denotes an experimental candidate, not a stable trading
release. **Do not publish it as rights-cleared or fully released.** No repository
LICENSE/NOTICE exists. The preserved copied framework declares AGPLv3 metadata,
with unresolved origin/notices; excluding it does not establish ownership or
licensing of every retained wrapper. GitHub source archives include the full
tree, so a narrow wheel does not clear full-source redistribution obligations.

The per-path ledger covers 1,158 scripts by syntax/hash/heuristic scan and marks
manual inspection separately. In particular, 958 copied-framework scripts and
the nested framework/integration suites remain outside runtime qualification;
passing the top-level family is not whole-repository approval. Windows Python
3.13.5 was executed; other Python versions and operating systems remain untested.
Current Pydantic/datetime deprecation warnings remain visible.

No brokerage account connection, authenticated snapshot, transaction, order,
money/security setting change, market matching, independently durable freshness
authority, live kill switch or profitability study was performed or authorized.
Synthetic fills are simulation inputs. No CI success or unattended live operation
is implied. Stable release remains blocked on rights/provenance, broader manual
review, platform/GUI qualification and independent recovery/freshness controls.
