# PROJECT STATE

Last Updated: 2026-03-19

## Project Vision & Architecture

### Vision
Build a scalable, multi-asset algorithmic trading platform that supports:
- Crypto trading via CCXT-enabled exchanges.
- Stock trading via Alpaca.
- Strategy development and monitoring through a Streamlit interface.
- AI-assisted analysis, strategy orchestration, and operational decision support via a LangChain-powered agent.
- Reliable deployment on Render with PostgreSQL for persistent state, analytics, and operational logs.

### Core Architecture (Target)
1. **Presentation Layer (Streamlit UI)**
	- Strategy controls (enable/disable, risk profile, symbols, timeframes).
	- Portfolio and PnL dashboards.
	- Signal inspection and execution audit views.
	- System health and bot status panels.

2. **AI Agent Layer (LangChain)**
	- Interprets user intents and market context.
	- Produces constrained, explainable trade recommendations.
	- Coordinates with strategy and execution modules using guardrails.
	- Writes rationale and action traces to logs/database.

3. **Strategy & Signal Layer**
	- Pluggable strategy modules (technical, statistical, ML-assisted).
	- Shared indicator/signal interface for both crypto and equities.
	- Backtest-forward parity as a design goal (same signal logic where possible).

4. **Execution Layer**
	- **CCXT adapter** for crypto order routing.
	- **Alpaca adapter** for stock order routing.
	- Unified broker abstraction for order placement/cancel/status.
	- Risk checks before execution (position sizing, max drawdown, exposure limits).

5. **Data & Persistence Layer (PostgreSQL + SQLAlchemy)**
	- Tables for positions, orders, fills, signals, strategy runs, and agent decisions.
	- Migrations and schema versioning from early phase.
	- Historical market data references and bot telemetry.

6. **Deployment Layer (Render Plan)**
	- Phase 1: Local development and paper trading.
	- Phase 2: Render web service for Streamlit app and worker service for bot loop.
	- Phase 3: Managed PostgreSQL on Render; secrets managed in environment variables.
	- Phase 4: Monitoring, alerts, and autoscaling tuning.

## Current Tech Stack

- **Language:** Python 3.x
- **UI:** Streamlit
- **ORM / DB Access:** SQLAlchemy
- **Database (target):** PostgreSQL (local dev DB now, Render Postgres later)
- **AI Orchestration:** LangChain
- **Execution Integrations (planned):** CCXT (crypto), Alpaca (stocks)
- **Deployment Target:** Render

## Directory Structure

### Current Workspace
```
Personal Trader/
├── .gitignore
└── PROJECT_STATE.md
```

### Planned Project Layout (Initial Blueprint)
```
Personal Trader/
├── app/
│   ├── ui/                      # Streamlit pages/components
│   ├── agent/                   # LangChain agent tools/prompts/flows
│   ├── strategies/              # Signal generation modules
│   ├── execution/               # CCXT/Alpaca broker adapters + order manager
│   ├── risk/                    # Position sizing and risk constraints
│   ├── data/                    # Market data clients + preprocessing
│   ├── db/                      # SQLAlchemy models/session/repositories
│   ├── services/                # Bot loop, schedulers, orchestration services
│   └── config/                  # Settings, env loading, constants
├── scripts/                     # Utility scripts (seed, migration helpers, etc.)
├── tests/                       # Unit/integration tests
├── alembic/                     # DB migration config/files
├── requirements.txt
├── render.yaml                  # Render service definitions (later phase)
└── PROJECT_STATE.md
```

## Completed Tasks

- [2026-03-19] Initialized `PROJECT_STATE.md` as persistent memory for architecture, stack, structure, and progress logs.
- [2026-03-19] Defined target multi-layer system architecture (UI, AI agent, strategy, execution, data, deployment).
- [2026-03-19] Established planned repository layout for scalable local-to-Render evolution.
- [2026-03-19] Implemented hardcoded Circuit Breaker risk module with daily drawdown kill-switch and enforced position sizing limits.
- [2026-03-19] Integrated risk gates into scheduler and execution flow so AI proposals and live trade execution are blocked when failsafes trigger.
- [2026-03-19] Added initial automated tests for `CircuitBreaker` behavior (`tests/test_risk_manager.py`).
- [2026-03-19] Updated project documentation for Alpha 1.1 in `README.md` with architecture, local runbook, deployment context, and test usage.

## Next Steps

- [ ] Add migration workflow (Alembic) before production schema evolution on Render PostgreSQL.
- [ ] Expand test coverage for scheduler loop, execution service, and AI proposal staging edge cases.
- [ ] Persist structured risk incidents to database for audit/compliance and monitoring dashboards.
- [ ] Replace placeholder Alpaca execution adapter internals with production order routing and response handling.
- [ ] Add CI pipeline (lint + tests + compile checks) for automated quality gates on each push.

## Operating Rule (Persistent)

At the end of every major code generation or task, provide exact markdown updates for the **Completed Tasks** and **Next Steps** sections so this file remains the single source of truth across sessions.
