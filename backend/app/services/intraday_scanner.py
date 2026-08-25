"""Intraday scanner — evaluates the configured intraday universe against
the intraday strategy using real recent intraday candles.

Read-only: it produces a per-symbol view of the current setup (trend, VWAP
position, momentum, volume, and the resulting BUY/SELL/HOLD state). It never
executes anything; the orchestrator is what turns a scan result into a
risk-checked order.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.market_data.base import MarketDataError, MarketDataProvider
from app.market_data.factory import get_market_data_provider
from app.strategies.base import BaseStrategy, StrategySignal
from app.strategies.intraday_vwap_momentum import IntradayVwapMomentumStrategy

# Enough recent calendar days to always cover the strategy warm-up on any
# interval, while staying far inside the provider's 60-day intraday window.
_SCAN_LOOKBACK_DAYS = 5


class IntradayScanResult:
    def __init__(
        self,
        symbol: str,
        signal: StrategySignal | None,
        latest_price: float | None,
        latest_bar_time: datetime | None,
        is_stale: bool,
        error: str | None = None,
    ) -> None:
        self.symbol = symbol
        self.signal = signal
        self.latest_price = latest_price
        self.latest_bar_time = latest_bar_time
        self.is_stale = is_stale
        self.error = error


class IntradayScanner:
    def __init__(
        self,
        settings: Settings | None = None,
        provider: MarketDataProvider | None = None,
        strategy: BaseStrategy | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or get_market_data_provider()
        self.strategy = strategy or IntradayVwapMomentumStrategy()
        self.tz = ZoneInfo(self.settings.market_timezone)

    def scan_symbol(self, symbol: str) -> IntradayScanResult:
        try:
            candles = self.fetch_recent_candles(symbol)
        except MarketDataError as exc:
            return IntradayScanResult(symbol, None, None, None, is_stale=True, error=str(exc))

        if not candles:
            return IntradayScanResult(
                symbol, None, None, None, is_stale=True, error="No intraday candles returned."
            )

        latest = candles[-1]
        is_stale = self.is_stale(latest.timestamp)
        signal = self.strategy.generate_signal(symbol, candles)
        return IntradayScanResult(
            symbol=symbol,
            signal=signal,
            latest_price=latest.close,
            latest_bar_time=latest.timestamp,
            is_stale=is_stale,
        )

    def scan_all(self) -> list[IntradayScanResult]:
        return [self.scan_symbol(symbol) for symbol in self.settings.intraday_symbols]

    def fetch_recent_candles(self, symbol: str) -> list:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=_SCAN_LOOKBACK_DAYS)
        return self.provider.get_historical_data(
            symbol, interval=self.settings.intraday_timeframe, start=start, end=end
        )

    def is_stale(self, latest_bar_time: datetime) -> bool:
        age = datetime.now(timezone.utc) - latest_bar_time
        return age > timedelta(minutes=self.settings.intraday_max_staleness_minutes)
