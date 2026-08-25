from datetime import datetime

from sqlalchemy import DateTime, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.enums import AutonomousTradingState


class IntradayAutonomousState(Base):
    """Persisted RUNNING/PAUSED/STOPPED/ERROR state for the intraday
    autonomous trader — entirely separate from `AutonomousState` (the daily
    SMA(10/30) trader's state). Starting/stopping one never affects the
    other."""

    __tablename__ = "intraday_autonomous_state"

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
