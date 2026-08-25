from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import RiskDecisionType


class RiskDecisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    signal_id: int
    decision: RiskDecisionType
    reason: str
    timestamp: datetime
