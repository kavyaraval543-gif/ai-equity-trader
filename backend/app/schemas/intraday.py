from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import AutonomousTradingState, ExitReason, SignalType, TradeSide
from app.schemas.backtest import HISTORICAL_DISCLAIMER
from app.schemas.market_session import MarketSessionOut
from app.schemas.portfolio import PortfolioOut

NET_OF_COSTS_NOTE = (
    "All returns below are NET of simulated transaction costs and slippage — "
    "not gross price movement. This is paper-trading research only, not investment advice."
)


# --- scanner ---


class IntradayScanResultOut(BaseModel):
    symbol: str
    signal_type: SignalType | None = None
    confidence: float | None = None
    reason: str | None = None
    indicator_data: dict | None = None
    market_price: float | None = None
    latest_bar_time: datetime | None = None
    is_stale: bool = False
    error: str | None = None


# --- autonomous status ---


class IntradayRiskConfigOut(BaseModel):
    max_trades_per_day: int
    max_simultaneous_positions: int
    max_capital_per_trade_pct: float
    max_daily_loss_pct: float
    max_consecutive_losses: int
    cooldown_minutes: int
    no_entry_minutes_before_close: int


class IntradayExitConfigOut(BaseModel):
    stop_loss_percent: float
    target_percent: float
    trailing_stop_enabled: bool
    trailing_stop_percent: float
    max_holding_minutes: int
    force_close_at_session_end: bool


class IntradayAutonomousStatusOut(BaseModel):
    state: AutonomousTradingState
    reason: str | None
    updated_at: datetime
    emergency_stop: bool
    scheduler_running: bool
    cycle_interval_seconds: int
    position_monitor_interval_seconds: int
    last_successful_cycle_at: datetime | None
    last_failed_cycle_at: datetime | None
    last_error: str | None
    last_skip_reason: str | None
    last_monitor_run_at: datetime | None
    last_monitor_error: str | None
    open_position_count: int
    # Live daily counters, so the dashboard can show "how close to the
    # limit" rather than just the static configured limits.
    trades_today: int
    max_trades_per_day: int
    realized_pnl_today: float
    max_daily_loss_pct: float
    consecutive_losses: int
    max_consecutive_losses: int
    in_cooldown: bool


class IntradayTradingStatusOut(BaseModel):
    trading_mode: str
    emergency_stop: bool
    strategy_names: list[str]
    market_data_provider: str
    symbols: list[str]
    interval: str
    portfolio: PortfolioOut
    open_position_count: int
    autonomous: IntradayAutonomousStatusOut
    market_session: MarketSessionOut
    exit_config: IntradayExitConfigOut
    risk_config: IntradayRiskConfigOut


# --- manual run-cycle ---


class IntradaySymbolCycleResult(BaseModel):
    symbol: str
    status: str  # "ok" | "market_data_error" | "execution_error"
    signal: str | None = None  # SignalType value, e.g. "BUY"/"SELL"/"HOLD"
    risk: str | None = None  # "APPROVED" | "REJECTED"
    trade_id: int | None = None
    error: str | None = None


class IntradayRunCycleResult(BaseModel):
    started_at: datetime
    completed_at: datetime
    symbols: list[IntradaySymbolCycleResult]
    signals_generated: int
    trades_executed: int
    errors: int
    portfolio: PortfolioOut


# --- backtesting ---


class IntradayBacktestCreate(BaseModel):
    symbol: str
    interval: str = "5m"
    start_date: date
    end_date: date
    starting_capital: float = 100_000.0
    transaction_cost_percent: float = 0.05
    slippage_percent: float = 0.05

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class IntradayBacktestTradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    side: TradeSide
    quantity: int
    price: float
    transaction_cost: float
    slippage_cost: float
    realized_pnl: float | None
    exit_reason: ExitReason | None
    timestamp: datetime


class IntradayBacktestRunOut(BaseModel):
    id: int
    symbol: str
    interval: str
    start_date: date
    end_date: date
    starting_capital: float
    ending_capital: float
    total_pnl: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float | None
    max_drawdown_pct: float
    longest_losing_streak: int
    trading_days: int
    trades_per_day: float
    transaction_cost_percent: float
    slippage_percent: float
    strategy_name: str
    strategy_params: dict
    created_at: datetime
    trades: list[IntradayBacktestTradeOut]
    disclaimer: str = HISTORICAL_DISCLAIMER
    net_of_costs_note: str = NET_OF_COSTS_NOTE
