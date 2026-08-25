from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import PortfolioKind, PositionStatus
from app.models.portfolio import Portfolio
from app.models.position import Position


def get_or_create_portfolio(
    db: Session, settings: Settings | None = None, kind: PortfolioKind = PortfolioKind.DAILY
) -> Portfolio:
    """Returns the portfolio for the given kind, creating it with the
    configured starting capital on first use. DAILY and INTRADAY portfolios
    are always separate rows — cash and positions never mix between them."""
    settings = settings or get_settings()
    portfolio = db.execute(
        select(Portfolio).where(Portfolio.kind == kind).order_by(Portfolio.id.asc())
    ).scalars().first()
    if portfolio is not None:
        return portfolio

    starting_capital = settings.intraday_starting_capital if kind == PortfolioKind.INTRADAY else settings.starting_capital
    portfolio = Portfolio(
        kind=kind,
        starting_capital=starting_capital,
        available_cash=starting_capital,
        current_equity=starting_capital,
        realized_pnl=0.0,
        unrealized_pnl=0.0,
    )
    db.add(portfolio)
    db.flush()
    return portfolio


def get_or_create_intraday_portfolio(db: Session, settings: Settings | None = None) -> Portfolio:
    return get_or_create_portfolio(db, settings, kind=PortfolioKind.INTRADAY)


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
