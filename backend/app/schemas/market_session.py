from datetime import datetime

from pydantic import BaseModel

from app.models.enums import MarketSessionStatus


class MarketSessionOut(BaseModel):
    status: MarketSessionStatus
    current_time: datetime
    timezone: str
    session_start: str
    session_end: str
    is_trading_allowed: bool
