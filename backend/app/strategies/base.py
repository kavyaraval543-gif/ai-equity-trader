"""Base strategy interface. Strategies consume normalized market data only
and never talk to a provider, the risk engine, or execution directly."""
from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel

from app.market_data.base import Candle
from app.models.enums import SignalType


class StrategySignal(BaseModel):
    """A strategy's output. Not yet risk-checked or executed."""

    symbol: str
    signal_type: SignalType
    confidence: float
    strategy_name: str
    reason: str
    indicator_data: dict
    market_price: float
    timestamp: datetime


class BaseStrategy(ABC):
    name: str

    @property
    @abstractmethod
    def warmup_period(self) -> int:
        """Minimum number of candles this strategy needs before it can
        produce a real (non-HOLD-for-insufficient-history) signal. Used by
        the backtest engine to size its pre-start_date warm-up fetch."""

    def get_params(self) -> dict:
        """The parameters this instance was configured with — recorded on
        every backtest run so results can be traced back to their exact
        configuration."""
        return {}

    @abstractmethod
    def generate_signal(self, symbol: str, candles: list[Candle]) -> StrategySignal:
        """Generate a signal from historical candles (most recent last).

        No strategy is claimed, or should be claimed, to guarantee profit.
        """
