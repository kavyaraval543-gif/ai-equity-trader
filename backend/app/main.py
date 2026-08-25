"""FastAPI application entry point."""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import backtests, health, market_data, portfolio, risk, signals, trades, trading
from app.core.config import get_settings
from app.database.session import SessionLocal
from app.scheduler.trading_scheduler import scheduler
from app.services.startup_recovery import run_startup_recovery

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    db = SessionLocal()
    try:
        run_startup_recovery(db, settings)
    finally:
        db.close()

    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown()


app = FastAPI(
    title=settings.app_name,
    description=(
        "Paper-trading-only automated equity trading platform. "
        "No real broker credentials or live order execution are present in this system."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(portfolio.router, prefix=settings.api_v1_prefix)
app.include_router(trades.router, prefix=settings.api_v1_prefix)
app.include_router(signals.router, prefix=settings.api_v1_prefix)
app.include_router(risk.router, prefix=settings.api_v1_prefix)
app.include_router(market_data.router, prefix=settings.api_v1_prefix)
app.include_router(trading.router, prefix=settings.api_v1_prefix)
app.include_router(backtests.router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict:
    return {
        "name": settings.app_name,
        "trading_mode": settings.trading_mode,
        "docs": "/docs",
    }
