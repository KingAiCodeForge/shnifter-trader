# Legacy Risk and Accounting Hardening — 17 October 2026

## Scope of this review branch

This is a safety-oriented refactor of Shnifter's **legacy, offline simulated**
risk and portfolio code. It is **not** an executable IBKR/Alpaca broker
integration, nor a finished autonomous paper trading system. Live execution
remains unavailable; the source has not been merged to main.

Affected modules:
- core/safe_risk_math.py (new pure risk calculations)
- core/risk_management.py (legacy manager delegates to safe math)
- core/shnifter_trade.py (persistent simulated trade_id)
- core/shnifter_data_manager.py (DB-first trades and unique-ID close)
- core/execution.py (read-only retry gate)
- shnifter_frontend/pnl_dashboard_popout.py (no automatic invented metrics)

## What changed

1. **Risk sizing:** Zero-distance/invalid long stops result in no position.
   The old fallback of 100 shares was removed. AI/LLM confidence does NOT
   scale an allocation. Whole-share sizing respects a <=2% nominal
   loss-to-stop budget, configured value/asset limits, and rejects NaN/inf.

2. **Projected exposure:** The safe risk helper evaluates the order's
   notional PLUS current holdings. Closing sells require proof of existing
   long quantity. A latched halt blocks new entries but can allow a
   *verifiable risk-reducing long sale*. Missing/inconsistent holdings,
   prices or quantity are rejected.

3. **Legacy order approval disabled by default:** The old RiskManager has
   no broker position-reconciliation adapter. Its
   position_snapshot_verified flag defaults to False. It is NOT a live
   security certificate: merely setting the boolean does not provide
   authenticated market data, broker cash or full outstanding-order state.
   Integrate and test such an adapter independently before enabling this
   internal gate. Never expose this flag to an LLM tool.

4. **Circuit breaker:** Day rollover no longer clears a risk halt.
   Recovery from a halt requires a separately reviewed operator procedure.
   The legacy risk latch is in memory only; durable paper/live latching
   belongs in a new event-sourced ledger.

5. **Retries:** Generic retry helper rejects functions that resemble
   submit, place, cancel, close or other state-changing verbs. It retries
   only named read operations on connection/timeout failures. An order
   submission with an uncertain acknowledgement must be RECONCILED by
   client-order ID and broker execution reports, not blindly submitted again.
   This remains a defensive heuristic, not a full broker transport.

6. **Simulated SQLite trade identity:** New Trade objects hold their exact
   SQLite row ID. Insertion commits before changing the in-memory portfolio.
   Closing a ticker with multiple matching open trades now requires trade_id.
   Close SQL updates only WHERE id=? AND status='open', requiring exactly one
   affected row. DB errors propagate; an in-memory close is not applied
   after a failed SQL close.

7. **Restart:** Rehydrate all persisted trades rather than only the newest
   100. Restore closed trade P&L, simulated balance and closed-P&L peak from
   saved records. Reject invalid saved states rather than silently
   ignoring hydration failure. Rebuilding closed P&L is NOT reconstructing
   a complete bank- or broker-grade cash ledger.

8. **Performance:** The legacy Profit Factor now uses
   gross realised wins / absolute gross realised losses. When no
   realised losing trades exist, expose null (undefined), not false
   positive or infinite precision. Legacy stored Sharpe is treated only
   as an old-schema placeholder: public get_trading_stats() exposes null.
   Accurate annualised Sharpe requires a dated, independently verified
   per-period NAV series; trade-by-trade P&L is not sufficient.

9. **Dashboard:** Missing live/statistical data no longer automatically
   displays random simulated P&L, trade rows, Sharpe, exposure or an
   invented "daily return" chart. Insufficient data is indicated as N/A.
   Intentional demo/mock methods remain available separately, but must
   not be confused with real performance.

## Tests

- Pure core.safe_risk_math module source was copied exactly to a local
  Python 3.13 sandbox. File length/FNV checksum matched the GitHub blob.
  15 offline tests passed, covering stop geometry, projected exposure,
  invalid holdings, halted entries, reducing sells, quote anomalies and
  multiple-value sizing constraints.
- tests/test_shnifter_safe_risk_math.py is committed with related cases.
- tests/test_shnifter_legacy_safety.py is committed with tests for the
  actual repo risk manager, retry helper and legacy DB. These need to be run
  against the complete repository (the working container lacks a full
  GitHub checkout and PySide6), so DO NOT mark those integration tests as
  passed in this document.
- No real order, live feed, GUI runtime, installed wheel, or full-suite test
  was performed by this review change.

## Unresolved release blockers

- Legacy DataManager still has an implicit starting balance ($100k), not an
  event-sourced or bank/broker-reconciled cash account.
- Stats use stale or entry-price substitutes if proper quote data is missing.
  No validated daily NAV/corporate-action/FX adjustments.
- Other legacy GUI demo functions, provider data paths and risk controls
  may still use fabricated values. Deliberately distinguish demo from live.
- SQLite data/shnifter_trading.db is tracked in the public repo; no migration
  or historical secret/licence audit occurred in this change.
- There is no authenticated live broker state reconciliation, order ACK /
  partial-fill state machine, cancel/fill race handling, or durable broker
  circuit-breaker recovery.
- The independent paper ledger and other PRs remain on separate branches;
  run a full combined test before integration/merge.

## Review and run

Run from a fully installed repository checkout:

    python -m unittest discover -s tests -p 'test_shnifter_safe_risk_math.py' -v
    python -m unittest discover -s tests -p 'test_shnifter_legacy_safety.py' -v

The new helper is *not* a replacement for a purpose-built broker ledger and
independent risk service. Treat any legacy simulation results as research.
