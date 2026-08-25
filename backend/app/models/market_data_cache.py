from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class MarketDataCache(Base):
    """One row per (provider, symbol, timeframe) tracking fetch freshness."""

    __tablename__ = "market_data_cache"
    __table_args__ = (UniqueConstraint("provider", "symbol", "timeframe", name="uq_market_data_cache_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    last_fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latest_market_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PriceCandle(Base):
    """Cached OHLCV bars, normalized across providers."""

    __tablename__ = "price_candles"
    __table_args__ = (
        UniqueConstraint("provider", "symbol", "timeframe", "timestamp", name="uq_price_candle_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
