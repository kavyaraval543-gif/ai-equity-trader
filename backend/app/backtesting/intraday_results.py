"""Plain result types for an intraday backtest run — no database/ORM coupling."""
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import ExitReason, TradeSide


class IntradayBacktestTradeResult(BaseModel):
    side: TradeSide
    quantity: int
    price: float
    transaction_cost: float
    slippage_cost: float
    realized_pnl: float | None
    exit_reason: ExitReason | None
    timestamp: datetime


class IntradayBacktestResult(BaseModel):
    symbol: str
    interval: str
    strategy_name: str
    strategy_params: dict
    starting_capital: float
    ending_capital: float
    total_pnl: float
    total_return_pct: float
    total_trades: int  # completed round trips
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win: float
    avg_loss: float
    profit_factor: float | None  # None when there are no losing trades to divide by
    max_drawdown_pct: float
    longest_losing_streak: int
    trading_days: int
    trades_per_day: float
    transaction_cost_percent: float
    slippage_percent: float
    trades: list[IntradayBacktestTradeResult]
