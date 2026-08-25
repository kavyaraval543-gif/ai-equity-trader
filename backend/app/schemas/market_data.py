from datetime import datetime

from pydantic import BaseModel


class SymbolMarketDataStatus(BaseModel):
    symbol: str
    provider: str
    connected: bool
    last_fetched_at: datetime | None
    latest_market_timestamp: datetime | None
    stale: bool
    detail: str


class MarketDataStatusOut(BaseModel):
    provider: str
    symbols: list[SymbolMarketDataStatus]
