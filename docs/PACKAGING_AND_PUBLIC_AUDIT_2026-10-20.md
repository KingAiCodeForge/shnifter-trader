# Packaging/public audit — 20 October 2026

The alpha package is a research CLI plus explicit local simulation only. Version
0.2.0a1 replaces misleading stable 1.0.0/MIT metadata. No licence grant is inferred:
there is no tracked LICENSE/NOTICE, and copied framework metadata declares AGPLv3
while its renamed licence URL is invalid. Full-source distribution remains on
hold until provenance and required notices are reconciled. The wheel and sdist
exclude `shnifter_platform_core/` and GUI/prototype trees, with explicit packaging
scope in setup.py and MANIFEST.in. This does not certify rights for every retained
line; downstream reuse/licensing still requires owner review.

The public source refs retain every original variant. Eight formerly tracked
local-state files are untracked, never deleted: the old SQLite database, two GUI
history files, a discovered-model configuration, pytest output and three .pyc
files. `PRESERVED_LOCAL_ARTIFACTS_2026-10-20.json` records bytes and SHA256 without
publishing the contents. Existing database data is not migrated, renamed or
replaced. The audit ledger records its nonempty nature without row contents.

`.gitignore` retains secret/environment/local-state exclusions and adds database
sidecars/config/runtime data exclusions. Only the reviewed public research test
family `tests/test_shnifter*.py` is eligible; unrelated local tests remain ignored.
No local/global excludes were broadened. Source manifests are metadata only.

Changed launch/setup scripts resolve their own quoted directory, preserve existing
virtual environments/prototypes, return nonzero on failure, and no longer change
execution policy or install every optional framework. `setup_dev_environment.py`
uses the active interpreter, subprocess argument lists and an explicit project
cwd; it does not modify package structure or auto-install copied frameworks.

GUI logs/history/configuration and legacy simulated DB use the user data directory
or absolute `SHNIFTER_DATA_DIR`. Existing cwd data is untouched. The GUI no longer
downloads NLTK data on import; missing sentiment data remains unavailable with a
clear message. MCP/GUI/network/platform qualification is recorded separately from
headless tests. `PUBLIC_SCRIPT_AUDIT_2026-10-20.json` provides per-file automated
syntax/import/hazard scans; automated scanning is not a manual correctness review.
