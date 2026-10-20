# The Shnifter Trader
by KingAi, Jason King, South Australia.
[![GitHub Repo](https://img.shields.io/badge/GitHub-KingAiCodeForge%2Fshnifter--trader-blue?logo=github)](https://github.com/KingAiCodeForge/shnifter-trader)

Im average at coding, this is a project i spent 2 hours on using vscode. idea was a ai powered auto trader called shnifter after the name of a mate i have on steam and discord, who said he wanted a autonomous trader... future intergrations will be openhands, autoMate, maybe openmanus or agentzero and agentgym. wired to the eventbus of course. EDA, more llm models and then a validation loop between ai models, or multi step system or parralel system. before output or commands issued.

The Shnifter Trader is an experimental stock-analysis and simulated-trading project for Windows desktops. Its GUI, models and legacy paper-account path still require integration work; it is **not** a validated autonomous trading system or a live brokerage trader. It leverages a multi-model decision system to provide real-time buy, sell, or hold recommendations using:

- **Technical Analysis** (SMA crossover)
- **Machine Learning** (Random Forest on price deltas)
- **Sentiment Analysis** (VADER on live news)
- **LLM Reasoning** (Ollama: llama3, gemma, etc.)

---

## 🚀 Features

- **Multi-Model Decision Engine**: Consensus voting (2 of 3 models must agree)
- **Trend Model**: SMA 20 vs SMA 50 crossover
- **ML Model**: RandomForest classifier on live price movements
- **Sentiment Model**: News-based polarity scoring
- **LLM Reasoning**: Human-readable explanations via Ollama
- **EventBus Architecture**: Centralized logging to GUI, file, and console
- **PySide6 GUI**: Multi-ticker input, log window, color-coded messages, charting
- **Scheduled GUI Analysis**: Requests analysis every 10 minutes while the app runs (not yet a restart-safe autonomous order loop)
- **Backtesting**: Deterministic long-only SMA crossover replay in GUI and CLI with auditable signals/fills and explicit transaction costs
- **Export**: Logs and last decisions to TXT, CSV, JSON

---

## 🛠️ Requirements

- Windows 10/11
- Python 3.13 (required)
- [Ollama](https://ollama.com/) (local LLM server)
- At least one Ollama model (e.g., llama3:8b)
- All Python dependencies in `requirements.txt`

---

## ⚡ Setup

1. **Clone the repository:**
   ```sh
   git clone https://github.com/KingAiCodeForge/shnifter-trader.git
   cd shnifter-trader
   ```
2. **Run the setup script (Windows):**
   ```sh
   start_shnifter_setup.bat
   ```
   - This creates a `.venv` using Python 3.13, upgrades pip, and installs all requirements.
   - **Python 3.13 is required. Do not use Python 3.11.**
3. **Start Ollama and pull a model:**
   ```sh
   ollama serve
   ollama pull llama3:8b
   ```
4. **Launch the app:**
   ```sh
   start_shnifter.bat
   ```
   - This activates the venv and runs the GUI.

**Other scripts:**
- `activate_venv.bat`: Activate the venv in your current shell (cmd or PowerShell)
- `open_venv_shell.bat`: Open a new cmd window with the venv activated

---

## 🖥️ Usage

- Enter tickers (e.g., AAPL, MSFT, SONY) in the GUI.
- View real-time recommendations, logs, and price charts.
- Use the menu to export logs or last decisions to TXT, CSV, or JSON.
- Use the backtest tool from the GUI for simple strategy simulation.
- Enable "Live Mode" for auto-refreshing charts.
- All logs are saved to `shnifter_log.txt`, `shnifter_log.csv`, and `shnifter_log.json`.

---

## 🧩 Architecture

- **EventBus**: Broadcasts DEBUG, ERROR, INFO events
- **EventLog**: Centralizes logs to GUI, file (`shnifter_log.txt`), and console
- **LLM Integration**: Uses Ollama for natural language feedback and reasoning
- **.bat Scripts**: For setup, launching, and environment management

---

## 🧪 Testing

Run tests with:
```sh
python -m unittest discover -s tests -p 'test_shnifter_replay.py' -v
python -m unittest discover -s tests -p 'test_shnifter_backtest_cli.py' -v
```

---

## 📄 License

MIT License

---

## 🖼️ Screenshot

![Shnifter Trader GUI](assets/screenshot_gui.png)

### Example: NVDA Price Chart

![NVDA Price Chart](assets/screenshot_nvda.png)

## 🧠 Advanced LLM Features

- **Dual-LLM Mode**: Analyzer and Verifier LLMs (selectable, independently) for self-checking, multi-pass trade validation
- **LLM Manager Popout**: Toggle dual-LLM mode, select models, and see real-time status (active/inactive)
- **Dynamic Model Detection**: Auto-detects available Ollama models, supports refresh
- **Menu Actions**: Run single, dual, or double-pass LLM analysis from the GUI
- **Event-Driven Everything**: All user actions, model changes, and analysis results are logged and visible in the Event Log popout

## 📈 Real-Time & Modular

- **Real-Time Analysis**: Multi-ticker, multi-threaded, with live log and chart updates
- **Modular Backend**: Easily extend with new models, providers, or strategies
- **Popout Windows**: Event log and LLM manager popouts for advanced control

## 🚦 How Dual-LLM Mode Works

1. **Analyzer LLM**: Generates a trade recommendation and reasoning
2. **Verifier LLM**: Critiques/confirms/revises the Analyzer's output
3. **Final Action**: Only after both passes is a trade signal generated and logged

I am building Shnifter Trader using custom, original code and ideas. Some inspiration comes from open source projects, but all code is refactored and original for Python 3.13.2.


---

## Headless CLI: first action (market historical)

The new CLI can fetch historical daily OHLCV records without importing the
PySide6 GUI, starting Ollama, or placing a paper/live trade. It reuses the
existing ShnifterBB -> yfinance price path, with one confirmed price provider.
This is the first of several planned CLI actions, not a complete autonomous bot.

From a source checkout with the Python dependencies installed:

```bash
python shnifter_cli.py --help
python shnifter_cli.py market historical --help
python shnifter_cli.py market historical --ticker AAPL --start 2026-01-01 --end 2026-10-01 --limit 20 --format json
python shnifter_cli.py market historical --ticker NVDA --start 2026-01-01 --end 2026-10-01 --format csv --output nvda_history.csv
```

After installing the project via pip, use `shnifter-trader` in place of
`python shnifter_cli.py`. The package console entry point is now wired to
`shnifter_cli:main` rather than the nonexistent GUI `main()` function.

Arguments: `--ticker` is one symbol; `--start` is inclusive and
`--end` is **exclusive** (YYYY-MM-DD). `--provider` currently
accepts only `yfinance`; `--limit` selects the most recent N bars; the default
is 100. `--format` chooses JSON or CSV. `--output` writes to a file,
and an existing file requires explicit `--overwrite`. The command exits nonzero
for rejected dates, empty price data, or provider errors. Missing numbers are
JSON null / empty CSV fields, not fabricated prices.

Offline synthetic regression tests:

```bash
python -m unittest discover -s tests -p test_shnifter_cli.py -v
```

Historical price fetching requires network access. Offline tests use a fake
fetcher; passing them does **not** prove live-feed reliability, execution,
backtesting quality, model profitability, or correct portfolio accounting.

**Important current limitations:** the legacy GUI backtest currently derives
profit, win rate, and trade count from random values. The old GUI/paper ledger
also has unverified integration and position-accounting behaviour. Do not
interpret its demo outputs as measured strategy performance. No live broker
actions are provided through the CLI. See `docs/CLI_ACTION_ROADMAP.md`.


## Deterministic historical replay (new)

**This is simulation, not real/autonomous brokerage execution.** The GUI's
previous backtest randomly generated profit, win-rate and trade counts.
That calculation is now replaced with a reproducible single-symbol, long-only
SMA-crossover replay. Results come from OHLCV rows, not random numbers.

Run from a Python source checkout (no Qt or Ollama is needed for this CLI action):

```bash
python shnifter_cli.py backtest run --csv prices.csv --ticker AAPL --fast 20 --slow 50 --initial-cash 10000 --max-position-pct 0.20 --stop-loss-pct 0.05 --take-profit-pct 0.10 --max-drawdown-pct 0.20 --fee-bps 10 --slippage-bps 5 --output backtest_report.json
```

CSV column header: `date,open,high,low,close,volume` (daily, ordered,
unique YYYY-MM-DD dates; prices >0, finite, consistent OHLC). Supply your
own **historical market-data file**. No included test fixture constitutes
real market data. Use `--overwrite` explicitly if replacing a JSON report.

The engine computes SMA crossovers only after the bar's close and fills orders
at the **next** bar's opening price. It includes adverse execution slippage
and fees, whole-share positions, maximum initial entry allocation, protective
stop/target exits, and a persistent-for-the-run drawdown halt that prevents
further entries. If both stop and target are inside the same bar, stop is
assumed first. Gap-through-stop fills at the worse open, not the stop price.

Reports include the deterministic run ID, settings, dated signals, fills,
completed trades, cash, mark-to-market equity, realised/unrealised P&L,
drawdown and ending open position. With no completed trades the win rate is
**null**, not a fabricated statistic. A final open position is never silently
closed at the last historical candle.

Limitations: one instrument, no shorts/fractional shares, no real-order fills,
no partial fills, volume constraints, market impact, dividends, holidays,
overnight borrow costs, or intrabar path reconstruction. This does **not**
demonstrate profitability or predict future returns. Strategy and risk
parameters are research knobs, not optimized defaults. Next milestone:
correct the durable SQLite paper-order ledger before enabling scheduled
order simulation.


## New: AI-agent-accessible research commands (review branch)

Shnifter now has a **shared, headless, read-only** action service:

- \`python shnifter_cli.py actions list\` returns a JSON capability catalogue.
- \`python shnifter_cli.py analysis signals --csv prices.csv --ticker AAPL --fast 20 --slow 50\` computes chronological SMA/RandomForest research signals.
- \`shnifter_agent_api.py\` exposes the same actions over local FastAPI HTTP.
- \`shnifter_agent_mcp.py\` exposes the same actions to compatible MCP hosts (optional SDK v2).
- The historical replay action is also available through this shared dispatcher.

The GUI's normal analysis no longer silently opens simulated positions or
invents performance metrics from model confidence. The headless RandomForest
does not assign the last price bar an imaginary next-day target. Its reported
probability-up score is **uncalibrated** and is not a risk-sizing instruction.
The old confidence-weighted Kelly helper is replaced with bounded sizing.

Read [agent integration details](docs/SHNIFTER_AGENT_INTERFACES.md) and
[AI coding-agent instructions](AGENTS.md).

**Security:** These research actions cannot place real or paper-account orders.
Never grant arbitrary model tool calls authority to submit live trades, run
generated shell code in the trading environment, change account limits or
read private credentials. The REST API defaults to loopback-only access without
a separately configured key. A broker/paper execution gateway is a later,
independently permissioned component.

**Validation:** Local synthetic tests cover CLI, HTTP authentication, signal
logic and the replay dispatcher. Full GUI, installed-wheel and MCP SDK host
integration tests are not yet complete. Profitability is unproven.


## Legacy risk/accounting safety changes (review branch)

The experimental legacy simulated-account manager is being hardened before
any autonomous order execution. This branch adds strict risk sizing, projected
exposure checks, a non-resetting daily risk halt, exact SQLite trade IDs,
transaction-first simulated trade updates and read-only network retries.
It also removes automatic random portfolio performance fallbacks in the
PnL dashboard. **The existing legacy risk manager refuses all order
approvals unless an independently reconciled position snapshot is present.**

Research signals are still NOT executable trades. Neither this branch nor
the paper-ledger prototype connects to a live broker. Existing historical
data, cached bid/ask estimates, full PySide6 startup, live market feeds,
partial fills and real account reconciliation remain unverified.

Run the focused local tests from a full checkout:

```bash
python -m unittest discover -s tests -p 'test_shnifter_safe_risk_math.py' -v
python -m unittest discover -s tests -p 'test_shnifter_legacy_safety.py' -v
```

See [Legacy Risk and Accounting Hardening](docs/LEGACY_RISK_ACCOUNTING_HARDENING_2026-10-17.md)
for scope, proof and outstanding blockers. Tests must pass in an integrated
environment before any release or merge.


## Research-only out-of-sample profitability screening

This experimental branch unifies the safe research, risk-helper, experiment-
registry and isolated SQLite paper-account modules. It does **not** contain
an authorised live broker or an established profitable trading strategy.

To test a fixed set of SMA strategies using chronological validation, held-out
future bars, matched buy-and-hold allocation, and explicit transaction-cost
stress:

    python shnifter_cli.py research gate --csv daily.csv --ticker AAPL --folds 3 --candidates 5:20,10:30,20:50,20:100 --fee-bps 10 --slippage-bps 5 --stress-multiplier 2 --output research_report.json

The JSON report records rejected candidates as well as positive-looking
backtests and always returns live_authorized=false. It can flag a strategy
for **further paper research**, never live authorisation. The evaluator is
a single-symbol SMA research tool; it does not verify quotes, dividends,
survivorship, fees, market impact, broker fills or point-in-time data.

Isolated paper-account CLI commands are also available:

    python shnifter_cli.py paper init --db paper_research.sqlite
    python shnifter_cli.py paper status --db paper_research.sqlite
    python shnifter_cli.py paper halt --db paper_research.sqlite --reason "Operator pause"

These do not submit real orders or use authenticated quotes. Do not use
the existing legacy trading SQLite database as the isolated paper ledger.

See docs/PROFITABILITY_EVIDENCE_GATE_2026-10-17.md for validation assumptions
and the remaining real-money release conditions.


## Opt-in research experiment registry

Historical backtests can now be preserved in a **separate local SQLite**
database with complete bar snapshots, full replay results, SHA256 content
hashes and a stable experiment ID. Recording is optional:

```bash
python shnifter_cli.py backtest run --csv historical_daily.csv --ticker AAPL --registry-db research_experiments.sqlite
python shnifter_cli.py experiments list --registry-db research_experiments.sqlite
python shnifter_cli.py experiments verify --registry-db research_experiments.sqlite --id YOUR_EXPERIMENT_SHA256
```

The backtest is still read-only by default; `--registry-db` is an explicit local
file write. Saved results are recomputed from the stored daily OHLCV history
and can be checked for accidental changes. **This does not validate the data
feed or guarantee any returns.** See
[Experiment Registry](docs/EXPERIMENT_REGISTRY_2026-10-17.md).

## Experimental package scope (20 October 2026)

Version `0.2.0a1` is an alpha for research CLI and explicit local paper simulation.
Install in a fresh environment with `python -m pip install .`; use `[market]`
for optional yfinance history, `[api]` for the local HTTP adapter, or `[agents]`
for the MCP SDK 1.29+ adapter (host qualification is reported separately). The wheel intentionally excludes
legacy GUI/prototype trees and the copied framework. GUI source checks are
reported separately; installing the wheel does not install the GUI application.
`requirements.txt` selects source-checkout GUI/development extras; it no longer
requests every experimental ML framework and broker SDK at once.

Runtime GUI logs/configuration and legacy simulation state use the user data
folder, or an absolute `SHNIFTER_DATA_DIR` override. No existing cwd `data/`
ledger is renamed, imported, or deleted. Set the override explicitly to inspect
an isolated fixture. Local databases/model discovery files remain ignored;
reviewed `tests/test_shnifter*.py` regressions are eligible for public tracking.
The setup/scaffold scripts preserve existing environments and prototype files.

No MIT licence is asserted: no repository licence file exists and copied
framework provenance/AGPL obligations require review before a full-source
release. See `docs/PACKAGING_AND_PUBLIC_AUDIT_2026-10-20.md` and the per-script
static ledger for exact scope and remaining limits.

The fresh combined source run passed 279 methods plus 174 subtests; the clean
installed-package checks passed 14/14. Exact scope, source/artifact hashes and
remaining release holds are recorded in
[Integration Qualification](docs/INTEGRATION_QUALIFICATION_2026-10-20.md).
For v1 database preservation, separate new v2 simulations and the limits of
detached rollback anchors, read
[Paper Checkpoints and Version 2](docs/PAPER_CHECKPOINT_AND_V2_2026-10-20.md).
These results qualify only the documented software research/paper scope.
