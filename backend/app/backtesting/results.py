"""Plain result types for a backtest run — no database or ORM coupling."""
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import TradeSide


class BacktestTradeResult(BaseModel):
    side: TradeSide
    quantity: int
    price: float
    transaction_cost: float
    realized_pnl: float | None
    timestamp: datetime


class BacktestResult(BaseModel):
    symbol: str
    strategy_name: str
    strategy_params: dict
    starting_capital: float
    ending_capital: float
    total_pnl: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown_pct: float
    buy_hold_return_pct: float
    transaction_cost_percent: float
    trades: list[BacktestTradeResult]
