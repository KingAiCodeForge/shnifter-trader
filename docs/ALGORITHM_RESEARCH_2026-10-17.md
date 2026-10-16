# Shnifter Trader — algorithm research beyond bandits, Kelly, PPO and VWAP

Research date: 2026-10-17 (Australia/Adelaide).
Scope: **research proposal**, not a tested performance result, algorithmic trading advice, or permission to deploy live broker orders.
Source baseline: `KingAiCodeForge/shnifter-trader`, with research branched from `review/deterministic-replay-20261017`.

## Executive finding

At small capital and daily swing timeframes, Shnifter's edge is more likely to come from reproducible **data quality + strategy selection + cost-aware abstention + independent risk control** than from custom neural bandits, PPO, Almgren–Chriss, millisecond order slicing, or agent debate. Those advanced methods can be researched in shadow mode without becoming live control paths.

**Selection of advanced sounding models is not evidence of trading edge.** The scientific experiment is whether a candidate beats a simple, investable benchmark on previously unseen time periods *after realistic fees, spreads, slippage, funding, dividends and FX*, without violating risk constraints.

## 1. Algorithms we have not meaningfully covered

| Candidate | What it changes | Minimum viable test | Priority |
| --- | --- | --- | --- |
| Time-series trend following / absolute momentum | Use price trend over multiple horizons, with cash/no-trade state | 20/50 SMA baseline versus 3-, 6- and 12-month trend rules, same costs | P1 |
| Cross-sectional momentum | Rank multiple assets on past relative performance, selecting a point-in-time universe | 6–12-month return ranking with a documented skip-month variant; ETFs before individual equities | P2 |
| Volatility targeting | Adjust exposure with **past** realised volatility, no future data | Compare fixed-notional versus rolling volatility-scaled exposure | P1 |
| Cost-aware abstention | Only act when estimated benefit clears all-in costs and forecast uncertainty | Count skipped actions and net outcomes under several cost assumptions | P1 |
| Probabilistic calibration | Turn out-of-sample model scores into testable probability estimates | Separate chronological train/calibration/test; log Brier score, log loss and calibration curves | P1 |
| Portfolio covariance shrinkage | Estimate asset co-movement with less noisy covariance than raw sample | Compare equal weights, inverse-vol weights and Ledoit–Wolf portfolio constraints | P2 |
| Scenario risk / Expected Shortfall (CVaR) | Explicitly budget loss under the worst fraction of scenarios | Historical/block-bootstrap stress of portfolio plus fixed correlated-gap scenarios | P2 |
| Simple expert weighting / Hedge | Weight existing strategy forecasts; distinguish full-information from bandit setting | Shadow score every eligible strategy over the same historical periods | P2 |
| Contextual bandit / Thompson sampling | Online choice among strategy candidates with partial feedback | Only after propensity logging, delayed rewards and off-policy evaluation | P3 |
| Change-point / regime monitoring | Detect distribution drift, allow abstention, don't proclaim future crises | Walk-forward monitoring of realised vol, correlation, features and predictive error | P2 |
| Causal news-event drift study | Ask whether tagged news predicts **tradable later** returns, not just immediate reaction | Point-in-time timestamped disclosures, first-seen feed, lagged trade at next available quote | P2 |
| Tax and corporate-action aware returns | Distinguish executable raw prices from total-return/research prices | Reconcile splits, dividends, delistings, borrow fees and currency conversion | P0 |
| Deflated Sharpe / data-snooping controls | Penalise trying many algorithms on one price history | Every candidate and parameter sweep registered before testing; never re-use the final holdout | P0 |
| Live implementation shortfall | Compare intended versus actual execution after arrival price, fees and FX | Paper-and-event replay first, later broker order/fill reconciliation | P2 |

## 2. Evidence strength — not a ranking of prospective profits

**Time-series momentum:** Hurst, Ooi and Pedersen examine long-run trend-following evidence across markets and historical regimes. Their institutional and futures evidence does not establish a profitable single-stock strategy or a particular implementation after modern trading costs.

- https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing
- https://research.cbs.dk/en/publications/a-century-of-evidence-on-trend-following-investing/

**Machine-learning features:** Gu, Kelly and Xiu report historical improvements from ML for asset pricing, with momentum, liquidity and volatility among useful predictive inputs. This does not imply that a random-forest trained on one asset's previous-day percent change will make money.

- https://academic.oup.com/rfs/article/33/5/2223/5758276

**Volatility scaling:** Moreira and Muir show historical benefits in several factor portfolios, with nonuniform results across factors and regimes. Shnifter must test scaling rather than assume it prevents all crashes.

- https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2659431

**2026 LLM evidence:** Lopez-Lira and Tang's Journal of Financial Economics paper finds that LLM news classifications can correspond strongly to **immediate reactions that cannot be traded after observing them**. Later drifts are weaker, net tradability is constrained by costs, and reported performance diminishes as LLM adoption increases. A 90% nontradable immediate-reaction hit rate is **not** a 90% trading win rate.

- https://www.sciencedirect.com/science/article/pii/S0304405X26001066
- https://www.sciencedirect.com/science/article/abs/pii/S0304405X26001066

**AI historical-memory leakage:** Models can recall information not available at an earlier decision time, giving apparently excellent but invalid LLM backtests.

- https://www.sciencedirect.com/science/article/pii/S0165176525004392

**Multiple testing:** Bailey et al.'s PBO and Deflated Sharpe approaches, White's Reality Check and Harvey–Liu–Zhu explain why the best of hundreds of tested strategies frequently wins by chance.

- https://papers.ssrn.com/sol3/Papers.cfm?abstract_id=2326253
- https://doi.org/10.2139/ssrn.2460551
- https://doi.org/10.1111/1468-0262.00152
- https://www.nber.org/papers/w20592

## 3. Specific corrections to the pasted 'institutional' designs

### Neural contextual bandits are not automatic alpha

- A bandit receives the chosen arm's reward and often not the unchosen arms' rewards. If every candidate strategy can be simulated under the *same* timestamped prices, Shnifter has richer **full-information** feedback and can compare simple expert weighting before using bandits.
- When evaluating logged bandit decisions, save observation time, eligible arms, context, action, selection probability/propensity, reward maturity time, reward including costs, policy hash and market regime.
- Consider inverse propensity scoring or doubly robust off-policy estimation. If the logged policy never chose an action in a given context, its counterfactual return cannot be determined merely by mathematical confidence.
- Do not let the bandit randomly try unvalidated strategies with real capital; exploration stays in shadow paper simulations.
- Source: https://proceedings.mlr.press/v70/wang17a.html

### Fractional Kelly and EVT do not predict crashes

- Binary Kelly: f* = (p*b - (1-p))/b. This assumes p and b accurately represent repeatable payoffs; an LLM 'confidence' is not a calibrated win rate, and a historical edge can vanish.
- EVT/GPD tail fitting estimates distribution features conditional on chosen data, threshold and stability assumptions. A high fitted tail risk does not establish that a crash is imminent tomorrow.
- Safer first baseline: cap exposure, volatility scaling, no-trade bands, scenario losses and a persistent risk latch. Treat Kelly as research-only until p, payoff asymmetry and uncertainty are validated out-of-sample.

### Adaptive VWAP / TWAP code has execution-accounting errors

- Rounding fractions to minute bins then adding the residual to the final bin can produce a negative or overly large last allocation. Use largest-remainder apportionment if doing *integer planning*.
- A slice is not fulfilled merely because `submit_order` returned. Outstanding fills, replacements and cancellations must be incorporated before issuing the next slice; planned quantity minus acknowledged fills minus live outstanding quantity determines remaining capacity.
- Midpoint limit orders aren't guaranteed passive fills, and blindly repeating an unfilled midpoint order can produce an unbounded queue of live open orders.
- Brokerage-native algorithms may be preferable to recreating execution microstructure, especially for small liquid-stock orders. IBKR already documents TWAP, Arrival Price and Percentage of Volume.
- https://www.interactivebrokers.com/docs/general/order-types/algorithmic-orders/ib-algorithms/twap
- https://www.interactivebrokers.com/docs/general/order-types/algorithmic-orders/ib-algorithms/arrival-price
- https://www.interactivebrokers.com/docs/general/order-types/algorithmic-orders/ib-algorithms/percentage-of-volume

### PPO, 'agent debate', and LLM confidence

- PPO can optimise to imperfections in a training simulator. A high reward in a model-based backtest is not an audited real-world edge.
- Two LLMs debating the same flawed headline are not statistically independent confirmation.
- Hard drawdown, cash, max orders and risk constraints must remain enforceable outside any trained network, regardless of whether risk penalties appear in the reward.
- LLM research should produce source-linked event extraction and a `NO_EVIDENCE` outcome, **never** a broker executable instruction.

## 4. A counterintuitive, high-value algorithm: choose not to trade

If the expected net advantage is not reliably positive, staying in cash beats paying spread and commissions. Define an explicit decision rule evaluated *before* constructing an order:

- `mu_hat`: model estimate of expected horizon return for the intended side.
- `c_all_in`: round-trip spread, slippage, commissions, tax, funding and FX assumptions.
- `uncertainty_buffer`: pre-registered safety discount based on holdout calibration.
- Only propose entry if `mu_hat - c_all_in - uncertainty_buffer > 0`.
- The estimate must originate in timestamp-correct observations; `mu_hat` isn't model confidence.

Example with purely illustrative numbers: 0.40% forecast return minus 0.15% total estimated execution cost and 0.30% uncertainty buffer yields -0.05%. **Do not trade**. The numbers are not actual IBKR fees or a Shnifter forecast.

## 5. Point-in-time research data schema

Minimum immutable record fields:

```text
instrument_id, symbol_at_time, exchange, currency, trading_calendar
source_id, data_version, source_published_at, vendor_available_at, first_seen_at
bar_start_at, bar_end_at, exchange_timezone, price_basis (raw/adjusted)
corporate_action_ref, universe_membership_asof, row_quality_flags
model_version, features_asof, decision_at, intended_fill_window
```

The *information availability time* must precede the strategy's decision time. Splits and dividends need special treatment, especially because executable prices and research-adjusted prices mean different things. Avoid using today's survivors as the historical investable universe.

- https://www.quantconnect.com/docs/v2/writing-algorithms/key-concepts/research-guide

## 6. Test design that deserves to be called an experiment

1. Register hypotheses and candidate parameters before running them. Keep a persistent trial registry.
2. Keep untouched chronological holdout(s); use walk-forward model fitting and a gap/embargo appropriate to the holding period. For overlapping labels, explicitly purge training events that leak into test outcomes.
3. Benchmark **buy-and-hold, cash, naive equal-weight, fixed SMA and a simple linear/logistic model** under identical calendars, assets, constraints and costs.
4. Compare gross and net return, benchmark-relative return, drawdown, turnover, worst gap, expected shortfall, profitability by regime, Brier/log loss and calibration, sample size and uncertainty intervals.
5. Stress slippage/fees, missing quotes, delayed news, order rejection, partial fills, corporate actions, disconnect and restart.
6. Count all tried strategy variants; use a selection-bias correction such as PBO/DSR where assumptions permit, and preserve the untouched final holdout.
7. Shadow deploy and compare predicted versus paper/broker-market outcomes. Manual written promotion of a particular immutable model artifact is required before any production permission.

Source references:
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html
- https://scikit-learn.org/stable/modules/generated/sklearn.covariance.LedoitWolf.html

## 7. What to build into Shnifter first

**P0 — correctness:** repair the RandomForest last-bar target bug and missing confidence; remove any fake performance data, establish timestamp-correct data snapshots, immutable trials and a verified replay ledger.

**P1 — scientifically testable algorithms:** time-series momentum versus the existing SMA; regime-agnostic volatility targeting; cost-aware `HOLD` threshold; chronological calibration for RandomForest and logistic regression.

**P2 — experiments:** cross-sectional momentum and sector rotation across a point-in-time asset universe; Ledoit–Wolf covariance constraint; portfolio expected shortfall; LLM news-event drift with timestamps and a no-LLM ablation; shadow full-information expert weighting.

**P3 — expensive/complex:** contextual bandits once logging propensity and delayed-reward handling are solved; true intraday VWAP/POV execution if participation warrants it; reinforcement learning only after simulator fidelity, competing baselines and independent risk testing.

## 8. Repo-specific engineering observations

- In `Multi_Model_Trading_Bot.py`, `get_ml_signal` labels the last row as -1 due to `np.where(df['close'].shift(-1) > df['close'], 1, -1)` even though the future target does not exist. It then trains and predicts on a row without a genuine outcome. Separate history used for training from the most recent unlabeled row used for inference.
- The RandomForest model currently has only `price_change` as an input. More trees aren't a meaningful substitute for causal, timestamp-available features.
- `core/shnifter_risk.py` calls an uncalibrated `confidence` the success probability in its Kelly computation. Stop doing so in any live sizing path.
- Named files `BacktestingMomentumTrading_module.py`, `sectorRotationStrategy_module.py` and `portfolioOptimizationUsingModernPortfolioTheory_module.py` currently return only generic summaries/data-point counts. Treat these as **stubs**, not working algorithms.
- `shnifter_replay.py` on the review branch is a useful deterministic single-asset SMA baseline but not yet a multi-asset, dividend/corporate-action aware, point-in-time execution engine.

**Research deliverable only** — no trader/live broker execution code or historical performance claim has been produced by this document.


## 9. Further 2026 evidence and implementable open-source references

### Live agent capability ≠ reliably profitable returns

- **AI-Trader** (Fan et al., Dec 2025) benchmarks multiple autonomous LLMs across U.S. stocks, A-shares and crypto; many agents had weak returns and risk management. Do not equate agent autonomy or model IQ with an investable edge.
  - https://arxiv.org/abs/2512.10971
- **Agentic Trading** (Xia et al., May 2026) surveyed 77 studies; in 19 closed-loop empirical studies, only 2 exposed time-consistent split protocols, 1 documented transaction costs, 1 dealt with universe/survivorship and none met their R3 reproducibility standard.
  - https://arxiv.org/abs/2605.19337
- **Sealed Joint Search / Agora** (Li et al., June 2026) reports a promising 91-day holdout after a research-agent system evolved factor and evaluator libraries, but authors note a single seed, short-biased concentration, and a limited holdout. Treat this as a *research mechanism worth replicating*, not proof of a durable live trading edge.
  - https://arxiv.org/abs/2606.29194
- **Multiplicity-aware evaluation of DRL** (2026) finds substantial Sharpe dispersion across random seeds; apparent algorithm superiority can disappear once multiple comparisons are accounted for.
  - https://doi.org/10.1016/j.jfds.2026.100205

### Existing tools to adapt, not blindly copy

- **Microsoft Qlib + RD-Agent**: experiment orchestration, automated factor mining, rolling model workflows and quant evaluation. Study adapters, research metadata and evaluation procedures; benchmark against Shnifter's own simpler pipelines.
  - https://github.com/microsoft/qlib
  - https://github.com/microsoft/RD-Agent
- **AlphaGen**: constrained symbolic formula mining, RL-generated factor expressions and genetic-programming baselines, including adaptations to Qlib.
  - https://github.com/ICT-FinD-Lab/alphagen
- **TradingAgents**: LangGraph-like multi-agent financial research, provenance and persistent decisions. Its own documentation says results vary and the framework is for research rather than guaranteed returns. The original authors are affiliated with UCLA and MIT, but it is not an officially endorsed hedge fund.
  - https://github.com/TauricResearch/TradingAgents
  - https://tradingagents-ai.github.io/
- **IBKR native algorithms**: Arrival Price / VWAP / TWAP / Percentage of Volume are broker-side features. For a small daily equity portfolio, prioritise correct order reconciliation and real spread/cost measurement before custom neural execution scheduling.
  - https://www.interactivebrokers.com/docs/general/order-types/algorithmic-orders/ib-algorithms/arrival-price

## 10. Shnifter self-evolution protocol (research sandbox, not autonomous broker modification)

### Boundary rules

1. **Author:** an LLM or genetic search proposes a typed formula/feature *specification*, tagged with prompt/model/version/source timestamps. It does not produce executable order-routing code.
2. **Compile in isolation:** the candidate may use only allowlisted arithmetic, lags and rolling transforms. No filesystem, shell, imports, network, broker SDK, API secrets, dynamic eval/exec or database write permissions. Reject malformed, expensive or data-leaking expressions before running.
3. **Register every attempt:** append an immutable entry with strategy digest, formula, parameters, data snapshot digest, feature availability cutoff, universe definition, trial ordinal, tests and code version. **Never record just the winners.**
4. **Train / validate:** run rolling forward research sets, purge overlapping outcome windows, account for data vendor publication latency, delistings, corporate actions, spreads and commissions. Test simple baselines under identical calendars.
5. **Use one sealed evaluator:** strategy authors cannot read or mutate final holdout labels, performance queries or acceptance conditions. If a held-out result influences later candidate generation, that dataset is no longer independent.
6. **Statistical gate:** preserve failed variants, use multiple-comparison awareness (DSR/PBO as suitable), require robustness to nearby parameter perturbations and trading-cost stress, measure net returns and uncertainty, not simulated gross profit.
7. **Shadow mode:** run multiple variants without placing orders. Record what each *would* have decided at each historical clock time. Model-selection weights and rewards update only when the relevant outcome window has fully elapsed.
8. **Paper approval:** a signed, versioned strategy artifact can enter the paper execution service, **not a live broker**, after passing fixed risk checks and evaluation policy.
9. **Live approval (later):** require deliberate human authorization to change an active live model version, with deployment rollback, broker reconciliation, per-instrument limits and separate permissions for research vs brokerage. Strategies may be autonomous within a preapproved deployed release; agents cannot directly increase limits or self-modify broker code.

### Why this constraint matters

Running hundreds of candidate models through a mutable evaluator tends to select bugs in the evaluator, survivorship leakage, and unmodelled transaction-cost assumptions. The real innovation is independently sealed evaluation and a complete trial history, not unbounded self-writing logic.

LLM-retrieved news and webpages are **untrusted data**, not instructions. Treat potential prompt injections as malicious inputs; retrieved text must not be allowed to request tools, alter risk parameters, leak account credentials, or approve a trade.
- https://openai.com/index/prompt-injections/

### Fixed evidence schema for a candidate

\`\`\`json
{
  "candidate_id": "sha256-of-canonical-research-spec",
  "candidate_version": "immutable-version",
  "strategy_family": "time-series-momentum",
  "hypothesis": "testable statement, including horizon",
  "feature_spec": "typed and allowlisted operators only",
  "data_snapshot_sha256": "content-addressed-dataset",
  "instrument_universe_asof": "timestamp and membership reference",
  "publication_available_at": "earliest usable time",
  "train_range": "date interval",
  "validation_range": "date interval",
  "sealed_test_ref": "opaque reference; not directly readable by candidate author",
  "trial_number": 1,
  "benchmark_id": "benchmark-spec-digest",
  "risk_policy_hash": "immutable-bounds-digest",
  "research_state": "PROPOSED"
}
\`\`\`

The sample IDs are placeholders. This is a schema proposal, not a running registry or proof of valid alpha.

## 11. What "better than expected" would actually mean

- Shnifter can replay the *same research artifact* twice with identical decisions and audit outputs.
- It can say **NO TRADE** when projected net advantage is insufficient or current data has expired.
- It cannot accidentally train on data published after its decision timestamp.
- It can attribute realised or paper-simulated performance to the exact candidate, model, data and policy revision, including failures.
- It demonstrates better *out-of-sample net performance/risk* than buy-and-hold, cash, and fixed strategies under the same constraints in enough observations to estimate uncertainty.
- A corrupt feed, duplicate webhook, crashed instance or disconnected broker never bypasses the risk or reconciliation barrier.

**Not yet implemented here:** candidate compiler, event-sourced ledger, sealed evaluation runner, independent statistics, broker live execution and an autonomous optimizer. These must be separate reviewed engineering increments.
