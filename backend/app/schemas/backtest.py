from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, computed_field, field_validator

from app.models.enums import TradeSide

HISTORICAL_DISCLAIMER = (
    "Historical backtest results only. Past performance does not guarantee future returns; "
    "the highest-return configuration in this data is not automatically the best strategy going forward."
)


class BacktestCreate(BaseModel):
    symbol: str
    start_date: date
    end_date: date
    starting_capital: float = 100_000.0
    transaction_cost_percent: float = 0.1
    strategy: str = "SMA"
    # None means "use that strategy's own defaults" (SMA -> configured
    # sma_short_window/long_window, RSI -> configured rsi_period/thresholds).
    strategy_params: dict | None = None

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class BacktestTradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    backtest_run_id: int
    symbol: str
    side: TradeSide
    quantity: int
    price: float
    transaction_cost: float
    realized_pnl: float | None
    timestamp: datetime


class BacktestRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    start_date: date
    end_date: date
    starting_capital: float
    ending_capital: float
    total_return_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    max_drawdown_pct: float
    buy_hold_return_pct: float
    transaction_cost_percent: float
    strategy_name: str
    strategy_params: dict
    created_at: datetime

    @computed_field
    @property
    def total_pnl(self) -> float:
        return self.ending_capital - self.starting_capital


class CompareRequest(BaseModel):
    symbol: str
    start_date: date
    end_date: date
    starting_capital: float = 100_000.0
    transaction_cost_percent: float = 0.1

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


class StrategyComparisonResultOut(BaseModel):
    backtest_run_id: int | None  # null for the synthetic Buy & Hold row
    symbol: str
    strategy_name: str
    strategy_params: dict
    total_return_pct: float
    ending_capital: float
    total_trades: int
    win_rate: float
    max_drawdown_pct: float
    buy_hold_return_pct: float


class CompareResponse(BaseModel):
    symbol: str
    start_date: date
    end_date: date
    starting_capital: float
    transaction_cost_percent: float
    results: list[StrategyComparisonResultOut]
    disclaimer: str = HISTORICAL_DISCLAIMER


class MultiStockCompareRequest(BaseModel):
    start_date: date
    end_date: date
    starting_capital: float = 100_000.0
    transaction_cost_percent: float = 0.1


class MultiStockStrategyAverageOut(BaseModel):
    strategy_name: str
    strategy_params: dict
    avg_return_pct: float
    avg_max_drawdown_pct: float
    avg_buy_hold_return_pct: float
    per_stock: list[StrategyComparisonResultOut]


class MultiStockCompareResponse(BaseModel):
    start_date: date
    end_date: date
    starting_capital: float
    transaction_cost_percent: float
    symbols: list[str]
    averages: list[MultiStockStrategyAverageOut]
    disclaimer: str = HISTORICAL_DISCLAIMER
