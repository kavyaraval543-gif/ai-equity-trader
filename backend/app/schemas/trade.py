from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ExitReason, TradeSide


class TradeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    side: TradeSide
    quantity: int
    price: float
    transaction_cost: float
    realized_pnl: float | None
    strategy_name: str
    exit_reason: ExitReason | None
    timestamp: datetime
