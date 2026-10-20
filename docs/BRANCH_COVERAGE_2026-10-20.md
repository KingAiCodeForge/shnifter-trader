# Branch coverage audit — 20 October 2026

This audit compares the fetched public refs with exact PR #12 spine commit
`b70325b76fd61cc99d5c43dd87a0169aa70a5305`. It is a source comparison, not a test receipt.
No ref was deleted or rewritten. The original side branches remain distinct.

## Ref coverage

| Ref | Fetched commit | Relationship to original spine |
| --- | --- | --- |
| `main` | `10c3eb7f3a837c9119012974d6fde9c634b25cff` | ancestor |
| `research/algorithm-stack-20261017` | `80d3a77439060701dcec03248d941f5e6aa8366a` | content integrated; distinct ancestry retained pending merge |
| `review/experiment-registry-20261017` | `83aab0936db837192226bf813f0c030800676826` | content integrated; distinct ancestry retained pending merge |
| `review/risk-heat-hardening-20261017` | `91cfc9cb3335a5dc3787bec6ecac395ee3e3ff08` | content integrated; distinct ancestry retained pending merge |
| `review/paper-ledger-20261017` | `e95a2e2a5adf10af53b2cd4935e217e58ae0e360` | content integrated; distinct ancestry retained pending merge |
| `review/ibkr-safety-foundation-20261017` | `604aeecb03ba1e1b0a0077858219d9cb6236a044` | ancestor |
| `review/paper-ledger-trade-id-20261017` | `10c3eb7f3a837c9119012974d6fde9c634b25cff` | ancestor |

The integration spine includes PRs #1 → #2 → #4 → #7 → #8 → #9 → #10 → #11 → #12 by ancestry.
Side PR #3, #5 and #6 and the independent paper-ledger branch were copied into #9,
but their original commits were not ancestors of PR #12. Content equality alone
must not be described as merged ancestry; preserving these refs or making explicit
ancestry-preserving merge commits is necessary.

## Exact distinct side-branch coverage

For each branch, `git diff --name-only $(git merge-base <branch> <spine>) <branch>`
was enumerated, then each changed path's Git blob compared with the spine.

- PR #3 `research/algorithm-stack-20261017`: `docs/ALGORITHM_RESEARCH_2026-10-17.md`
  is byte-for-byte identical.
- PR #5 `review/experiment-registry-20261017`: `shnifter_experiments.py`,
  `shnifter_experiment_cli.py`, `tests/test_shnifter_experiments.py` and
  `docs/EXPERIMENT_REGISTRY_2026-10-17.md` are byte-for-byte identical.
- PR #6 `review/risk-heat-hardening-20261017`: `core/shnifter_risk.py`,
  `tests/test_shnifter_risk_fail_closed.py` and
  `docs/RISK_HELPER_FAIL_CLOSED_2026-10-17.md` are byte-for-byte identical.
- Independent `review/paper-ledger-20261017`: `shnifter_paper_ledger.py`,
  `shnifter_paper_cli.py`, `tests/test_shnifter_paper_ledger.py` and
  `tests/test_shnifter_paper_cli.py` are byte-for-byte identical.
- `review/ibkr-safety-foundation-20261017` equals the PR #2 commit and is already
  an ancestor. Its name does not establish any broker integration or validation.
- `review/paper-ledger-trade-id-20261017` equals fetched main and is already
  an ancestor. No unique prototype work exists at that ref.

## Nonidentical integration files

PR #5's `setup.py` retains both registry modules and adds later research/paper
modules. `shnifter_cli.py` retains `experiments` registration and dispatch and adds
analysis/research/paper/event groups. `shnifter_backtest_cli.py` retains the opt-in
registry flow, recomputation/receipt and declared-source handling; later changes
replace direct output writes with atomic shared-output helpers and protect input,
registry and SQLite sidecar aliases. The prior registry/output path checks are
superseded by stronger common checks, not silently removed functionality.

The independent paper branch's only nonidentical file is `shnifter_cli.py`:
`paper` registration/dispatch remains and later groups are added. Its no-broker
boundary is retained.

Three unique PR #5 documentation sections had been dropped in the integration
spine. This qualification restores their exact original text append-only:

- `AGENTS.md`: “Experiment registry for coding agents”.
- `README.md`: “Opt-in research experiment registry”.
- `docs/CLI_ACTION_ROADMAP.md`: “Experiment registry — 2026-10-17”.

These restore examples and the distinction between explicit CLI file recording,
read-only MCP/REST, unverified source labels and research-only results.

## Test inventory and remaining scope

The original spine contains 20 `tests/test_shnifter*.py` files, including all
side-branch regressions named above. Its earlier focused receipts do not include
all legacy and GUI tests. In particular `test_shnifter_core.py` imports legacy
trade, paper, credentials and config services; `test_shnifter_table_widget.py`
instantiates QWidget objects, and full discovery requires a QApplication with
an appropriate Qt platform in a process-isolated run. Headless/focused success
alone must not be reported as GUI or full-repository success.

No tests were run as part of this source-only audit. Qualification receipts from
fresh source/installed/GUI execution must be reported separately. No assertion
of broker reconciliation, live execution, financial profitability, sudden-power
loss recovery or externally trusted checkpoint freshness follows from this audit.
