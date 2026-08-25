from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import PositionStatus
from app.models.portfolio import Portfolio
from app.models.position import Position


def get_or_create_portfolio(db: Session, settings: Settings | None = None) -> Portfolio:
    """Phase 2 runs a single paper portfolio; this returns it, creating it
    with the configured starting capital on first use."""
    settings = settings or get_settings()
    portfolio = db.execute(select(Portfolio).order_by(Portfolio.id.asc())).scalars().first()
    if portfolio is not None:
        return portfolio

    portfolio = Portfolio(
        starting_capital=settings.starting_capital,
        available_cash=settings.starting_capital,
        current_equity=settings.starting_capital,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    db.add(portfolio)
    db.flush()
    return portfolio


def recalculate_portfolio(db: Session, portfolio: Portfolio) -> None:
    """Recompute equity/unrealized P&L from open positions marked to their
    current (real, last-fetched) prices. Call after execution and after
    marking positions to market."""
    open_positions = db.execute(
        select(Position).where(Position.portfolio_id == portfolio.id, Position.status == PositionStatus.OPEN)
    ).scalars().all()

    market_value = sum(p.current_price * p.quantity for p in open_positions)
    portfolio.unrealized_pnl = sum(p.unrealized_pnl for p in open_positions)
    portfolio.current_equity = portfolio.available_cash + market_value
    db.add(portfolio)
