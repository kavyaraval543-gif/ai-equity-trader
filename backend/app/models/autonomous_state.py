from datetime import datetime

from sqlalchemy import DateTime, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.enums import AutonomousTradingState


class AutonomousState(Base):
    """Single-row table holding the persisted autonomous trading state so it
    survives backend restarts (see restart-recovery requirements)."""

    __tablename__ = "autonomous_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[AutonomousTradingState] = mapped_column(
        Enum(AutonomousTradingState, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=AutonomousTradingState.STOPPED,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
