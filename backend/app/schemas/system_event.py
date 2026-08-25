from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import SystemEventLevel


class SystemEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    level: SystemEventLevel
    category: str
    message: str
    details: dict | None
    timestamp: datetime
