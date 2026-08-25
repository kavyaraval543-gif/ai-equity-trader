"""Yahoo Finance market data provider for NSE-listed Indian equities.

Uses the `yfinance` library, which reads Yahoo Finance's public quote/chart
endpoints. No API key or account is required. This is real, provider-sourced
market data — not synthetic or randomly generated — but it is best-effort,
delayed data suitable for a paper-trading development system, not an
official exchange feed. If Yahoo cannot be reached or returns no data, this
provider raises MarketDataError; it never fabricates a price.
"""
import threading
import time
from datetime import datetime, timezone

import yfinance as yf

from app.market_data.base import Candle, MarketDataError, MarketDataProvider, PriceQuote, ProviderStatus
from app.market_data.symbols import to_yahoo_ticker


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo"

    def __init__(self, min_request_interval_seconds: float = 0.5) -> None:
        self._min_request_interval = min_request_interval_seconds
        self._lock = threading.Lock()
        self._last_request_at: float = 0.0
        self._last_successful_fetch: datetime | None = None
        self._last_error: str | None = None

    def _throttle(self) -> None:
        """Best-effort client-side rate limiting to avoid hammering Yahoo's endpoints."""
        with self._lock:
            elapsed = time.monotonic() - self._last_request_at
            wait = self._min_request_interval - elapsed
            if wait > 0:
                time.sleep(wait)
            self._last_request_at = time.monotonic()

    def get_latest_price(self, symbol: str) -> PriceQuote:
        ticker_symbol = to_yahoo_ticker(symbol)
        self._throttle()
        try:
            ticker = yf.Ticker(ticker_symbol)
            price = ticker.fast_info.last_price
            if price is None or price <= 0:
                raise MarketDataError(f"Yahoo Finance returned no valid last price for {ticker_symbol}")
        except MarketDataError:
            self._last_error = f"no valid price for {ticker_symbol}"
            raise
        except Exception as exc:  # noqa: BLE001 — any provider failure must surface as MarketDataError
            self._last_error = str(exc)
            raise MarketDataError(f"Failed to fetch latest price for {ticker_symbol}: {exc}") from exc

        now = datetime.now(timezone.utc)
        self._last_successful_fetch = now
        self._last_error = None
        return PriceQuote(symbol=symbol.upper(), price=float(price), timestamp=now, provider=self.name)

    def get_historical_data(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        ticker_symbol = to_yahoo_ticker(symbol)
        self._throttle()
        try:
            ticker = yf.Ticker(ticker_symbol)
            if start is not None:
                df = ticker.history(start=start, end=end, interval=interval, auto_adjust=False)
            else:
                df = ticker.history(period="1y", interval=interval, auto_adjust=False)
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            raise MarketDataError(f"Failed to fetch historical data for {ticker_symbol}: {exc}") from exc

        if df is None or df.empty:
            self._last_error = f"no historical data returned for {ticker_symbol}"
            raise MarketDataError(f"Yahoo Finance returned no historical data for {ticker_symbol}")

        candles: list[Candle] = []
        for ts, row in df.iterrows():
            py_ts = ts.to_pydatetime()
            if py_ts.tzinfo is None:
                py_ts = py_ts.replace(tzinfo=timezone.utc)
            candles.append(
                Candle(
                    timestamp=py_ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=int(row["Volume"]) if row["Volume"] == row["Volume"] else 0,  # NaN guard
                )
            )

        self._last_successful_fetch = datetime.now(timezone.utc)
        self._last_error = None
        return candles

    def get_provider_status(self) -> ProviderStatus:
        return ProviderStatus(
            provider=self.name,
            connected=self._last_error is None and self._last_successful_fetch is not None,
            last_successful_fetch=self._last_successful_fetch,
            detail=self._last_error or "ok",
        )
