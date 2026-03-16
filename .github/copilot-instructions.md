# Shnifter Trader - AI Copilot Instructions

## Project Overview
The Shnifter Trader is an autonomous AI-powered trading bot built with PySide6, featuring a sophisticated EventBus architecture, multi-model decision systems, and modular analysis components. It's designed for Windows desktop deployment with Python 3.13+ and emphasizes real-time trading analysis through multiple AI providers.

## Key Architectural Patterns

### EventBus-Driven Architecture
- **Core Pattern**: All components communicate via `core/events.py` EventBus - a singleton with async processing, circuit breakers, and metrics
- **Event Types**: Use structured events like `ANALYSIS_COMPLETE`, `TRADE_SIGNAL`, `DATA_UPDATE`, `LLM_ACTIVITY`
- **Integration**: Components subscribe via `EventBus.subscribe(event_type, handler)` and publish with `EventBus.publish(event_type, payload, source)`
- **Wiring**: See `shnifter_event_wiring.py` for comprehensive event routing patterns between 50+ components

### Multi-Provider LLM System
- **Base Pattern**: All LLM providers inherit from `BaseLLMProvider` in `llm_manager/llm_providers.py`
- **Async Support**: Use `run_inference_async()` and `batch_inference()` for non-blocking operations
- **Error Handling**: Built-in retry logic with exponential backoff for OpenAI; circuit breakers for Ollama
- **Configuration**: LLM configs in `llm_config.json`; environment variables for API keys

### Modular Analysis System
- **Location**: `shnifter_analysis_modules/` - each module follows the `create_*_analyzer()` factory pattern
- **Integration**: Modules auto-register with the analysis pipeline via `shnifter_integration_manager.py`
- **Event Flow**: `analysis_request` → module execution → `analysis_complete` → UI update
- **Examples**: `portfolioOptimizationUsingModernPortfolioTheory_module.py`, `autogen_trading_agents.py`

### Frontend Architecture
- **Popouts**: All UI components extend base classes in `shnifter_frontend/` with registry pattern via `shnifter_popout_registry.py`
- **Data Widgets**: Use `ShnifterTableWidget` and `ShnifterPlotlyWidget` for consistent data presentation
- **Qt Integration**: `ShnifterEventEmitter` bridges EventBus to Qt signals for thread-safe UI updates

## Development Workflows

### Environment Setup
```bash
# Required: Python 3.13+ (NOT 3.11)
start_shnifter_setup.bat    # Creates .venv, installs requirements
start_shnifter.bat          # Activates venv and runs main app
```

### Testing Strategy
```bash
python test_runner.py       # Unified runner for both unittest and pytest
python -m pytest -v --html=shnifter_test_report.html  # HTML test reports
```

### Adding New Analysis Modules
1. Create module in `shnifter_analysis_modules/` following the factory pattern
2. Register events in `shnifter_event_wiring.py` 
3. Add integration logic to `shnifter_integration_manager.py`
4. Module auto-discovery happens via import in `Multi_Model_Trading_Bot.py`

### LLM Provider Integration
1. Inherit from `BaseLLMProvider` in `llm_manager/llm_providers.py`
2. Implement: `initialize()`, `run_inference()`, `run_inference_async()`, `get_status()`
3. Add provider to router in `llm_manager/llm_router.py`
4. Update UI selectors in `shnifter_frontend/enhanced_dropdown_components.py`

## Critical Integration Points

### Data Flow Architecture
```
Market Data → ShnifterBB → Analysis Modules → EventBus → LLM Providers → UI Components
```

### External Dependencies
- **Ollama**: Local LLM server (required) - models auto-discovered via `/api/tags`
- **ShnifterBB**: Financial data provider wrapper (`shnifterBB/shnifter_bb.py`)
- **AutoGen**: Multi-agent trading via `autogen_trading_agents.py`

### Critical Files for AI Agents
- `Multi_Model_Trading_Bot.py`: Main application entry point and GUI
- `core/events.py`: EventBus system with circuit breakers and async processing
- `shnifter_event_wiring.py`: Complete event routing map
- `shnifter_integration_manager.py`: Central component registry
- `llm_manager/llm_providers.py`: LLM provider interface and implementations

## Project-Specific Conventions

### Error Handling
- Use EventBus for error propagation: `EventLog.emit("ERROR", message, extra_data)`
- Circuit breaker pattern automatically isolates failing components
- LLM providers include retry logic with exponential backoff

### Async Patterns
- EventBus processes events asynchronously via background thread
- LLM inference supports both sync and async modes
- UI updates via Qt signals to maintain thread safety

### Configuration Management
- Environment variables for API keys (`OPENAI_API_KEY`)
- JSON configs for LLM models and analysis parameters
- Registry pattern for dynamic component discovery

### Code Organization
- `core/`: Fundamental systems (events, data models, configuration)
- `shnifter_frontend/`: All UI components with consistent base classes
- `shnifter_analysis_modules/`: Pluggable analysis components
- `llm_manager/`: LLM abstraction layer with multiple providers
- `providers/`: External data source integrations

When extending this codebase, always integrate with the EventBus system, follow the factory patterns for analysis modules, and ensure proper async/sync handling for LLM operations. The system is designed for high modularity and real-time performance in financial markets.
