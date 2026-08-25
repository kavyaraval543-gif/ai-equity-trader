from datetime import datetime

from pydantic import BaseModel

from app.schemas.autonomous import AutonomousStatusOut
from app.schemas.market_session import MarketSessionOut
from app.schemas.portfolio import PortfolioOut
from app.schemas.risk import RiskDecisionOut
from app.schemas.signal import SignalOut
from app.schemas.trade import TradeOut


class SymbolCycleResult(BaseModel):
    symbol: str
    status: str  # "ok" | "market_data_error" | "execution_error"
    signal: SignalOut | None = None
    risk_decision: RiskDecisionOut | None = None
    trade: TradeOut | None = None
    error: str | None = None


class RunCycleResult(BaseModel):
    started_at: datetime
    completed_at: datetime
    symbols: list[SymbolCycleResult]
    signals_generated: int
    trades_executed: int
    errors: int
    portfolio: PortfolioOut


class ExitConfigOut(BaseModel):
    stop_loss_percent: float
    target_percent: float
    trailing_stop_enabled: bool
    trailing_stop_percent: float
    force_close_at_session_end: bool


class TradingStatusOut(BaseModel):
    trading_mode: str
    emergency_stop: bool
    strategy_names: list[str]
    market_data_provider: str
    symbols: list[str]
    portfolio: PortfolioOut
    open_position_count: int
    autonomous: AutonomousStatusOut
    market_session: MarketSessionOut
    exit_config: ExitConfigOut
