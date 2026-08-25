# AI Equity Trader

A modular, **paper-trading-only** automated equity trading platform, focused initially on
Indian equities. No real broker credentials or live order execution exist in this system.

## Architecture

```
Market Data → Strategy Engine → Signal → Risk Engine → Execution Engine → Portfolio → Database → Dashboard
```

No component is permitted to bypass the risk engine. See [`backend/app`](backend/app) for the
module breakdown (`market_data`, `strategies`, `risk`, `execution`, `backtesting`, etc.) — each
is independent and swappable behind an interface.

## Status: Phase 1

This phase sets up the project skeleton only:

- Monorepo structure (`backend/`, `frontend/`)
- FastAPI backend with configuration, database connection, and health/status endpoints
- Next.js + TypeScript + Tailwind frontend with a dashboard shell that calls the backend
- PostgreSQL via Docker Compose
- Environment configuration (`.env.example`)

Trading logic (strategies, risk engine, paper execution, positions, backtesting, full API/DB
models) is **not yet implemented** and lands in later phases.

## Prerequisites

- Docker + Docker Compose (recommended), **or**
- Python 3.12+, Node.js 20+, and a local PostgreSQL 16 instance

## Running locally with Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

- Backend: http://localhost:8000 (docs at http://localhost:8000/docs)
- Frontend: http://localhost:3000
- Postgres: localhost:5432 (user/pass/db: `trader`/`trader`/`ai_equity_trader`)

## Running locally without Docker

### Database

Start a local PostgreSQL 16 instance and create a database/user matching `.env`
(defaults: user `trader`, password `trader`, db `ai_equity_trader`).

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
cp ../.env.example ../.env    # if not already created
uvicorn app.main:app --reload
```

Backend runs at http://localhost:8000.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at http://localhost:3000.

## Verifying Phase 1

1. **Backend health**: `curl http://localhost:8000/api/v1/health` → `{"status": "ok", ...}`
2. **System status**: `curl http://localhost:8000/api/v1/system/status` → reports backend,
   database connectivity, and current trading mode (`paper`).
3. **API docs**: open http://localhost:8000/docs (auto-generated OpenAPI/Swagger UI).
4. **Frontend**: open http://localhost:3000 — the dashboard shell loads and displays a live
   "System Status" card fetched from the backend.

## Running backend tests

```bash
cd backend
pytest
```

## Safety

1. Paper trading only — no real-money execution exists in this codebase.
2. No real broker credentials are stored or required.
3. The risk engine (added in a later phase) will be the only path to execution; no component
   may bypass it.
4. A global emergency stop flag (`EMERGENCY_STOP`) is reserved in configuration.
5. No strategy in this system is claimed, or should be claimed, to guarantee profit.
