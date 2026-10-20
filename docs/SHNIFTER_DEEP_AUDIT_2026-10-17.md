# Shnifter Trader — code and release-gate audit

Audit date: 2026-10-17 ACDT
Scope: live GitHub source plus focused local offline tests.
Base: review/analysis-core-refactor-20261017, which itself depends on draft PR #2 -> PR #1.
This branch is NOT merged. No broker accounts or real money were accessed.

**Overall release status: NOT READY FOR LIVE TRADING.** Neither a positive
unit-test count nor code review proves full GUI operation, true market-data
freshness, economic alpha, broker reconciliation, or operating safety.

## Confirmed high-severity findings

### A1. Legacy simulated trades are not accounted for by unique position

File: core/shnifter_data_manager.py, around lines 306–343 and 495–522 (main).
- close_trade() selects the first matching in-memory ticker position.
- Its SQL update uses WHERE ticker=? AND status='open', closing **every**
  open SQLite row for that ticker, not the one in-memory position.
- _save_trade() and _update_trade_in_db() swallow SQL exceptions while
  the caller continues updating in-memory state.
- _load_data() loads only the newest 100 trades, not all open trades, so
  risk exposure can disappear when enough newer rows accumulate.
- A closed trade can appear both in trade_history and portfolio.closed_trades;
  get_trade_history() concatenates both lists.
- get_model_performance(name) and get_market_data(ticker) call
  dataclasses.asdict({}) if no matching entry exists, raising TypeError.
- Simulated P&L and stats derived from cached entry prices if no fresh quote.
- profit_factor formula based on mean win/mean loss is not the standard
  sum(gross wins)/abs(sum(gross losses)). The "Sharpe" uses per-trade
  returns without frequency standardisation and must not be marketed as
  annualised performance.

**Action:** stop using this legacy database for authoritative positions.
Use a separately tested ledger with durable position/execution IDs, strict
DB errors, full restart reconciliation and measured mark-to-market values.
Back up legacy SQLite and design a one-way migration with checksums before
any migration. The review/paper-ledger branch is a useful isolated prototype,
not a completed broker ledger.

### A2. Unsafe legacy risk layer remains present

File: core/risk_management.py (main and review branches inherited from main).
- calculate_position_size multiplies cash risk by (0.5 + AI confidence).
  Uncalibrated LLM scores must NOT increase live allocation.
- A zero-distance stop returns 100 units rather than refusing sizing.
- validate_order compares existing total exposure against the limit without
  adding the intended new opening order consistently.
- _reset_daily_counters() can clear circuit_breaker_active on date rollover,
  inconsistent with a manual-reset latch.
- _validate_price_sanity() approves a market order without checking
  current_price and no robust finite/positive guard exists in validation.
- core/execution.RateLimiter.execute_with_backoff() retries an arbitrary
  async function on broad Exception. NEVER use generic automatic retries
  for non-idempotent broker order submissions with unknown network outcome.

**Action:** isolate/disable the legacy execution path; consolidate around
one audited risk service and order-state machine. Preserve explicit permission
for risk-reducing actions during a halt. Retry only verified-idempotent reads,
and reconcile unknown broker order states before any repeat submission.

The hardened core/shnifter_risk.py in PR #6 is a DIFFERENT module; its fixes
do not automatically fix core/risk_management.py.

### A3. Paper execution is currently simplified, not a broker simulator

Branch: review/paper-ledger-20261017, shnifter_paper_ledger.py.
- It persists signal/order/fill/position IDs, idempotency keys and cash
  adjustments transactionally, which is valuable.
- Every accepted BUY/SELL is marked FILLED in one step, with no resting,
  acknowledged, rejected-by-broker, partial-fill, cancel-pending or
  unknown-transmission states.
- Maximum realised loss is not a daily mark-to-market equity drawdown;
  losses on held positions are not included.
- Manual source_at and price do not prove quote freshness or actual
  market-data provenance. The paper ledger is intentionally not wired to
  IBKR. Do not mistake timestamp validation for feed authentication.

**Action:** add a broker-style state machine and an independent simulator
able to represent split fills, rejected orders, timeouts, reconnects and
cancel/fill races before introducing live adapters.

## Correctness and operations

### A4. GUI's market-data label and timing are misleading

Files: Multi_Model_Trading_Bot.py, providers/yfinance_provider.py.
- GUI 'intraday/live' analysis asks for three years of history through
  yfinance.download without an intraday interval (default is daily).
- GUI uses end_date=datetime.now().strftime('%Y-%m-%d'). yfinance's end
  parameter is **exclusive**, so this excludes the named end date.
- Host-local Adelaide time and US-exchange dates can diverge. Market-open,
  session-close and stale-data checks require the exchange calendar and an
  explicit timezone.
- yfinance uses auto_adjust=True; past adjusted prices are useful for
  research but cannot be assumed to equal historical executable quotes
  around splits and dividends.
- Model / LLM explanation requests are still subject to provider failures,
  and GUI dual-LLM mode remains synchronous on the Qt thread.

Official end-date semantics:
https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html

**Action:** surface "last completed daily bar" timestamp; determine exchange
calendar and effective end-exclusive dates before fetching; verify stale data
before *any* automated decision. Keep GUI network/LLM calls off the UI thread.

### A5. Live state across PRs is not integrated

Checked six GitHub draft PRs:
1. CLI historical data -> main
2. Deterministic replay -> PR #1 branch
3. Algorithm research -> PR #2 branch
4. Agent interfaces -> PR #2 branch
5. Experiment registry -> PR #4 branch
6. Risk helper hardening -> PR #4 branch

PRs #5 and #6 are **parallel children**, not a merged integrated build.
The paper-ledger branch is based on the earlier replay branch and the IBKR
safety-foundation branch currently contains no additional commits beyond
its base. Do not claim paper, research registry, risk and agent interfaces
have passed a single end-to-end test as a merged application.

**Action:** integrate PR #1 -> #2 -> #4, reconcile #5 and #6 in a new
temporary integration branch, then bring the tested paper ledger in only
after adapting it to the shared service/CLI. Do not merge to main until
source install, GUI, MCP host and all offline suites run together.

### A6. Input validation defect, fixed on THIS review branch

Before this change, shnifter_actions.invoke_action('market.historical',
{'ticker': 123, ...}) attempted .strip() on an integer and threw an
unhandled AttributeError. The read-only FastAPI adapter handled ValueError
but not AttributeError, producing server errors instead of 422 validation.
Boolean window parameters and the string 'false' as use_ml were also
unvalidated or accepted as truthy.

Fixed in shnifter_actions.py:
- Strict string checks for ticker and date arguments;
- integer-only fast, slow, min_labeled; boolean-only use_ml;
- safe error construction for mixed-type unknown keys;
- reject a non-string action name;
- retain deny-by-default unsupported action names.

Regression: **60 focused tests passed**, including 7 additional audit
tests, with 49 unittest subtest invocations, in a local Python 3.13.5
workspace containing the same changed action source. Tests use synthetic
bars and FastAPI TestClient; no market/broker access.
The broader repository and actual MCP host handshake remain untested.

### A7. Public repository hygiene and commercial provenance

GitHub tree (main):
- A tracked data/shnifter_trading.db (24,576 bytes) and three .pyc compiled
  bytecode files. Delete from future commits AND inspect history before
  deciding whether any records/credentials require remediation.
- README/setup.py claim MIT, but no root or nested LICENSE/NOTICE/COPYING
  file exists in the checked main tree.
- Large shnifter_platform_core tree contains many imports of shnifter_core;
  it needs a separate package-install/smoke test and source provenance
  audit before describing it as fully functioning. Renaming or rewriting
  licensed OpenBB code does not erase upstream licence obligations.
- core/credentials.py writes user_settings.json credentials as plaintext.
  Do not store broker API keys there; use OS-backed secrets/keychain or
  restricted server secret management and never commit them.
- setup.py declares Python >=3.9 and classifiers 3.9–3.13 although project
  scripts target 3.13 and current modules use syntax/requirements requiring
  newer versions. Verify actual supported versions against package wheels.
- No current evidence of leaked credentials was established by this review;
  filenames/public tree existence alone cannot prove or disprove leaks.

**Action:** verify upstream licences and dependency notices, remove tracked
generated/private data in a dedicated commit, audit git history, fix version
metadata and build an installed-wheel smoke-test before commercial release.

### A8. Security and operational boundaries

- The API validates parameters AFTER FastAPI/Pydantic parses the body;
  the '500k' guard is not a true ASGI-level request-size limit.
- Stdio MCP uses the current SDK v2 style (MCPServer): this is supported by
  the official 2026 Python SDK documentation. Actual Claude/Codex handshake
  was **not** tested in this environment.
- API authentication can allow requests with a configured key regardless
  of source address; safe public deployment additionally needs TLS,
  secret management, rate/request quotas, logging and an upstream gateway.
- GUI query_ollama() sends HTTP without a timeout in main; may wait
  indefinitely while the GUI is stopping.
- Demo portfolio generation uses random trades; keep it clearly isolated
  and never mix its invented metrics with real backtests or live analytics.

Official MCP source: https://github.com/modelcontextprotocol/python-sdk

## Test evidence

Re-ran local offline subsets on 2026-10-17:
- Agent + registry/replay subset: 60 pytest test cases passed, 49 subtests;
- Paper-ledger/replay subset: 28 test cases passed, 10 subtests;
- Separate risk-helper subset: 11 test cases passed, 13 subtests.

These are overlapping tests from separate **partial workspaces**. They are
NOT 99 independent end-to-end tests and do not validate combined PRs.
PySide6, yfinance, and the MCP SDK are not installed in the local test
container; full GUI/feed/host tests remain blocked.

## Next five release gates

1. Create a true combined integration branch. Run import/installation
   smoke tests, all relevant unit tests, CLI help, and MCP host handshake.
2. Decommission or harden legacy core/risk_management.py and the global
   core/shnifter_data_manager.py instance so they cannot bypass the new
   independent paper ledger.
3. Create broker-like paper order states and reconciliation:
   NEW, PENDING_SUBMIT, ACK, PARTIAL, CANCEL_PENDING, CANCELLED,
   FILLED, REJECTED, UNKNOWN; duplicate/late/out-of-order events.
4. Ensure event timestamps, exchange calendars, corporate actions,
   fees, currency, quotes and equity are correct. Register failed
   experiments and sealed chronological holdout evaluations.
5. Only then stage an IBKR paper session with persisted kill switch,
   measured order discrepancy alarms, operator recovery and no live
   account permissions. Hold off real-money execution until those
   gates and a separately approved live-risk policy pass.

No user capital, brokerage credentials, real trade or deployment was touched.
