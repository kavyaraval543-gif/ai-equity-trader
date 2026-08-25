"""Provider-agnostic market data abstraction.

Every provider must normalize its output into these shapes so the strategy
and orchestration layers never see provider-specific formats.
"""
from abc import ABC, abstractmethod
from datetime import datetime

from pydantic import BaseModel


class Candle(BaseModel):
    """A single normalized OHLCV bar."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


class PriceQuote(BaseModel):
    """A normalized latest-price quote."""

    symbol: str
    price: float
    timestamp: datetime
    provider: str


class ProviderStatus(BaseModel):
    """Health/status snapshot for a market data provider."""

    provider: str
    connected: bool
    last_successful_fetch: datetime | None
    detail: str


class MarketDataError(Exception):
    """Raised when real market data cannot be obtained.

    Callers (the trading orchestrator, in particular) must treat this as a
    hard stop: no fallback or synthetic price may be substituted.
    """


class MarketDataProvider(ABC):
    """Abstract interface every market data provider must implement."""

    name: str

    @abstractmethod
    def get_latest_price(self, symbol: str) -> PriceQuote:
        """Return the latest available real price for `symbol`.

        Raises MarketDataError if a real price cannot be obtained.
        """

    @abstractmethod
    def get_historical_data(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        """Return normalized historical OHLCV candles for `symbol`.

        Raises MarketDataError if historical data cannot be obtained.
        """

    @abstractmethod
    def get_provider_status(self) -> ProviderStatus:
        """Return the provider's current connectivity/health status."""
