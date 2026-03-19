# Personal Trader (Alpha 1.1)

Multi-asset algorithmic trading platform for crypto and stocks with:
- Streamlit operations dashboard
- AI trade analyst and proposal staging
- Human-in-the-loop approvals
- SQLAlchemy persistence (SQLite local, PostgreSQL-ready for Render)
- Hard risk failsafes via Circuit Breaker controls

## Current Architecture

- `ui/app.py`: Command Center, Deep Analytics, Mission Control
- `ai_agent.py`: LLM-driven analysis and proposal generation
- `scheduler.py`: APScheduler worker for periodic AI proposal staging
- `execution/service.py`: guarded execution gateway
- `core/risk_manager.py`: strict circuit-breaker risk controls
- `database/models.py`: ORM models for records, proposals, settings

## Risk & Security (Alpha 1.1)

- Daily drawdown kill-switch automatically disables `is_trading_active`.
- Position size enforcement caps AI proposals using database risk limits plus hardcoded safety ceilings.
- Execution route is risk-gated before any live order call.
- Broker key hardening reminders are documented in `execution.py`:
  - use Trade-Only API scopes
  - enable broker-side IP whitelisting

## Local Development

1. Create/install environment:
	- `python -m venv .venv`
	- `source .venv/bin/activate`
	- `pip install -r requirements.txt`
2. Initialize database:
	- `python -m database.init_db`
3. Start dashboard:
	- `streamlit run ui/app.py`
4. Start scheduler worker:
	- `python scheduler.py`

## Tests

- Run tests: `python -m pytest -q`
- Current suite includes circuit breaker guardrail tests in `tests/test_risk_manager.py`.

## Deployment

- Render infrastructure is defined in `render.yaml`.
- Set required environment variables (LLM, Alpaca, News API, Finnhub) in Render service settings.