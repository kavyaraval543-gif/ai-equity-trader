from datetime import datetime

from sqlalchemy import DateTime, Enum, Float, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.models.enums import PortfolioKind


class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    # DAILY (the original SMA(10/30) autonomous trader) or INTRADAY — kept as
    # entirely separate portfolios so cash/positions never mix between the
    # two strategies unless a caller explicitly queries both.
    kind: Mapped[PortfolioKind] = mapped_column(
        Enum(PortfolioKind, native_enum=False, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PortfolioKind.DAILY,
    )
    starting_capital: Mapped[float] = mapped_column(Float, nullable=False)
    available_cash: Mapped[float] = mapped_column(Float, nullable=False)
    current_equity: Mapped[float] = mapped_column(Float, nullable=False)
    realized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unrealized_pnl: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
