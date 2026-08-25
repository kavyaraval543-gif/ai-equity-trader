from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.models.enums import PositionStatus


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    starting_capital: float
    available_cash: float
    current_equity: float
    realized_pnl: float
    unrealized_pnl: float
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def total_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl


class PositionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    quantity: int
    entry_price: float
    current_price: float
    stop_loss: float | None
    target: float | None
    peak_price: float
    unrealized_pnl: float
    status: PositionStatus
    opened_at: datetime
    closed_at: datetime | None
