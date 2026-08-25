from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import SignalType


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    signal_type: SignalType
    confidence: float
    strategy_name: str
    reason: str
    indicator_data: dict
    market_price: float
    timestamp: datetime
