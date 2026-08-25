"""Application configuration, loaded from environment variables."""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root .env (backend/app/core/config.py -> backend/app -> backend -> root),
# resolved absolutely so it loads regardless of the current working directory
# (e.g. running uvicorn from backend/ vs. the project root).
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # General
    app_name: str = "AI Equity Trader"
    environment: str = "development"
    debug: bool = True

    # Safety — paper trading only in v1. This must never be flipped by config alone;
    # a live adapter would require a separate, explicit code change.
    trading_mode: str = "paper"

    # Database
    database_url: str = "postgresql+psycopg://trader:trader@localhost:5432/ai_equity_trader"

    # API
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Market data — real data only, no mock/simulated/fallback provider exists.
    market_data_provider: str = "yahoo"
    market_data_symbols: list[str] = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    market_data_timeframe: str = "1d"
    # How old the latest fetched bar may be before it's treated as stale and
    # blocks new trades. Generous enough to tolerate weekends/long holidays.
    market_data_max_staleness_hours: float = 96.0
    historical_lookback_days: int = 180
    historical_cache_ttl_minutes: int = 15

    # Strategy — SMA crossover (the live autonomous trader's strategy; do not
    # change this to affect autonomous trading — that's Phase 4B's explicit
    # guardrail. Backtesting/comparison instantiate strategies with their own
    # explicit parameters and never read or write these).
    sma_short_window: int = 10
    sma_long_window: int = 30

    # Strategy — RSI (backtesting/comparison only; the live autonomous trader
    # does not use this strategy).
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0

    # Risk engine
    starting_capital: float = 1_000_000.0
    risk_max_position_pct: float = 0.10
    risk_max_simultaneous_positions: int = 5
    risk_max_trades_per_day: int = 10
    risk_max_daily_loss_pct: float = 0.03
    risk_transaction_cost_bps: float = 5.0

    # Autonomous scheduler
    trading_cycle_interval_seconds: int = 300
    position_monitor_interval_seconds: int = 60
    # Seeds the initial AutonomousState row on first run only (fresh installs
    # start STOPPED unless this is set). Runtime state lives in the database
    # and is controlled via /api/v1/trading/autonomous/{start,pause,stop}.
    autonomous_trading_enabled: bool = False

    # Indian market session (see app/services/market_session_service.py — keep
    # session rules here, not hardcoded, so they can be adjusted without
    # touching trading logic).
    market_timezone: str = "Asia/Kolkata"
    market_session_start: str = "09:15"
    market_session_end: str = "15:30"
    market_holidays: list[str] = []  # ISO date strings, e.g. "2026-01-26"

    # Exit management — configurable risk controls, not a claim of profitability.
    stop_loss_percent: float = 2.0
    target_percent: float = 4.0
    trailing_stop_enabled: bool = False
    trailing_stop_percent: float = 1.0
    force_close_at_session_end: bool = False

    # Emergency stop — when true, no NEW entries may be created anywhere in the
    # system. Existing positions continue to be monitored and protective exits
    # (stop-loss/target/trailing-stop) still fire — see app/risk/engine.py.
    emergency_stop: bool = False

    # --- Phase 5: intraday (separate from the daily SMA autonomous trader) ---

    # Intraday universe — independently configurable from the daily one,
    # defaults to the same 5 liquid stocks.
    intraday_symbols: list[str] = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"]
    intraday_timeframe: str = "5m"  # "5m" or "15m"
    # Yahoo Finance hard limit for sub-daily intervals (empirically confirmed:
    # "The requested range must be within the last 60 days"). Requests beyond
    # this are rejected with a clear error, never silently truncated.
    intraday_max_lookback_days: int = 60
    intraday_max_staleness_minutes: float = 30.0

    # Strategy — Intraday VWAP + momentum (backtesting/autonomous intraday only;
    # never used by the daily SMA(10/30) autonomous trader).
    intraday_trend_fast_ema: int = 9
    intraday_trend_slow_ema: int = 21
    intraday_rsi_period: int = 14
    intraday_rsi_min: float = 50.0
    intraday_rsi_max: float = 75.0
    intraday_volume_avg_window: int = 20
    intraday_volume_multiplier: float = 1.2

    # Intraday risk engine — layered on top of (never bypassing) the shared
    # RiskEngine checks. See app/risk/intraday_engine.py.
    intraday_starting_capital: float = 100_000.0
    intraday_risk_max_trades_per_day: int = 5
    intraday_risk_max_simultaneous_positions: int = 1
    intraday_risk_max_capital_per_trade_pct: float = 0.50
    intraday_risk_max_daily_loss_pct: float = 0.02
    intraday_risk_max_consecutive_losses: int = 3
    intraday_risk_cooldown_minutes: int = 15
    # No new entries within this many minutes of session close.
    intraday_no_entry_minutes_before_close: int = 15

    # Intraday exit management
    intraday_stop_loss_percent: float = 1.0
    intraday_target_percent: float = 1.5
    intraday_trailing_stop_enabled: bool = False
    intraday_trailing_stop_percent: float = 0.5
    intraday_max_holding_minutes: int = 120
    intraday_force_close_at_session_end: bool = True

    # Intraday transaction costs + slippage (backtesting and live paper fills)
    intraday_transaction_cost_percent: float = 0.05
    intraday_slippage_percent: float = 0.05

    # Intraday autonomous scheduler — separate from the daily scheduler/state,
    # defaults OFF, and is never auto-enabled by anything in this system.
    intraday_cycle_interval_seconds: int = 60
    intraday_position_monitor_interval_seconds: int = 30
    intraday_autonomous_trading_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
