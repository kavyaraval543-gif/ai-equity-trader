"""Historical-data caching + staleness checks on top of a MarketDataProvider.

Real market data is always sourced from the configured provider. This layer
only avoids re-fetching unchanged data too often (via a short cache TTL) and
tracks freshness metadata — it never invents or substitutes data.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.market_data.base import Candle, MarketDataError, MarketDataProvider, PriceQuote
from app.models.market_data_cache import MarketDataCache, PriceCandle


class MarketDataService:
    def __init__(self, provider: MarketDataProvider, db: Session, settings: Settings | None = None) -> None:
        self.provider = provider
        self.db = db
        self.settings = settings or get_settings()

    def get_latest_price(self, symbol: str) -> PriceQuote:
        """Always fetches fresh — a "latest price" call is meaningless if cached."""
        return self.provider.get_latest_price(symbol)

    def get_historical_data(self, symbol: str, timeframe: str = "1d") -> list[Candle]:
        """Return historical candles, using the DB cache when it's still fresh.

        Raises MarketDataError if no real data is available and the cache is
        empty or stale — callers must not substitute synthetic data.
        """
        symbol = symbol.upper()
        cache_row = self.db.execute(
            select(MarketDataCache).where(
                MarketDataCache.provider == self.provider.name,
                MarketDataCache.symbol == symbol,
                MarketDataCache.timeframe == timeframe,
            )
        ).scalar_one_or_none()

        now = datetime.now(timezone.utc)
        cache_fresh = (
            cache_row is not None
            and (now - cache_row.last_fetched_at) < timedelta(minutes=self.settings.historical_cache_ttl_minutes)
        )

        if cache_fresh:
            cutoff = now - timedelta(days=self.settings.historical_lookback_days)
            rows = self.db.execute(
                select(PriceCandle)
                .where(
                    PriceCandle.provider == self.provider.name,
                    PriceCandle.symbol == symbol,
                    PriceCandle.timeframe == timeframe,
                    PriceCandle.timestamp >= cutoff,
                )
                .order_by(PriceCandle.timestamp.asc())
            ).scalars().all()
            if rows:
                return [
                    Candle(
                        timestamp=r.timestamp, open=r.open, high=r.high, low=r.low, close=r.close, volume=r.volume
                    )
                    for r in rows
                ]
            # Cache row exists but no candles (shouldn't normally happen) — fall through to refetch.

        start = now - timedelta(days=self.settings.historical_lookback_days)
        candles = self.provider.get_historical_data(symbol, interval=timeframe, start=start, end=now)

        self._upsert_candles(symbol, timeframe, candles)
        self._upsert_cache_metadata(symbol, timeframe, now, candles[-1].timestamp)
        self.db.commit()

        return candles

    def _upsert_candles(self, symbol: str, timeframe: str, candles: list[Candle]) -> None:
        if not candles:
            return
        rows = [
            {
                "provider": self.provider.name,
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume,
            }
            for c in candles
        ]
        stmt = pg_insert(PriceCandle).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["provider", "symbol", "timeframe", "timestamp"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
            },
        )
        self.db.execute(stmt)

    def _upsert_cache_metadata(
        self, symbol: str, timeframe: str, fetched_at: datetime, latest_market_timestamp: datetime
    ) -> None:
        stmt = pg_insert(MarketDataCache).values(
            provider=self.provider.name,
            symbol=symbol,
            timeframe=timeframe,
            last_fetched_at=fetched_at,
            latest_market_timestamp=latest_market_timestamp,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["provider", "symbol", "timeframe"],
            set_={"last_fetched_at": stmt.excluded.last_fetched_at, "latest_market_timestamp": stmt.excluded.latest_market_timestamp},
        )
        self.db.execute(stmt)

    def is_stale(self, latest_market_timestamp: datetime) -> bool:
        now = datetime.now(timezone.utc)
        age = now - latest_market_timestamp
        return age > timedelta(hours=self.settings.market_data_max_staleness_hours)

    def get_status(self, symbols: list[str], timeframe: str = "1d") -> list[dict]:
        """Freshness snapshot per symbol, for the /market-data/status endpoint."""
        provider_status = self.provider.get_provider_status()
        results = []
        for symbol in symbols:
            symbol = symbol.upper()
            cache_row = self.db.execute(
                select(MarketDataCache).where(
                    MarketDataCache.provider == self.provider.name,
                    MarketDataCache.symbol == symbol,
                    MarketDataCache.timeframe == timeframe,
                )
            ).scalar_one_or_none()
            if cache_row is None:
                results.append(
                    {
                        "symbol": symbol,
                        "provider": self.provider.name,
                        "connected": provider_status.connected,
                        "last_fetched_at": None,
                        "latest_market_timestamp": None,
                        "stale": True,
                        "detail": "no data fetched yet",
                    }
                )
                continue
            stale = self.is_stale(cache_row.latest_market_timestamp)
            # "Connected" means the pipeline is demonstrably working: either this
            # process has made a live call, or cached data (fetched by any process,
            # possibly before a restart) is still within freshness — a cache hit is
            # itself proof the provider was reachable recently.
            results.append(
                {
                    "symbol": symbol,
                    "provider": self.provider.name,
                    "connected": provider_status.connected or not stale,
                    "last_fetched_at": cache_row.last_fetched_at,
                    "latest_market_timestamp": cache_row.latest_market_timestamp,
                    "stale": stale,
                    "detail": provider_status.detail,
                }
            )
        return results
