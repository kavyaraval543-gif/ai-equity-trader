"""Restart recovery. Runs once at application startup.

Only loads existing state and recomputes derived values already backed by
the database — it never re-executes an old signal or creates a trade. Since
every trading cycle and monitor pass commits atomically (one commit per
pass), a crash mid-cycle simply rolls back that whole pass; there is no
partial state to "resume," which is what makes this idempotent by
construction rather than by explicit bookkeeping.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import PortfolioKind, PositionStatus, SystemEventLevel
from app.models.position import Position
from app.services import autonomous_control_service, intraday_control_service
from app.services.event_logger import log_event
from app.services.portfolio_service import get_or_create_portfolio, recalculate_portfolio


def _open_position_count(db: Session, portfolio_id: int) -> int:
    return db.execute(
        select(func.count(Position.id)).where(
            Position.portfolio_id == portfolio_id, Position.status == PositionStatus.OPEN
        )
    ).scalar_one()


def run_startup_recovery(db: Session, settings: Settings | None = None) -> dict:
    """Recovers both the daily and intraday portfolios independently. Each is
    only ever recomputed from its own already-persisted rows — no trade is
    re-executed and no prior signal is re-processed for either one."""
    settings = settings or get_settings()

    portfolio = get_or_create_portfolio(db, settings, kind=PortfolioKind.DAILY)
    open_position_count = _open_position_count(db, portfolio.id)
    recalculate_portfolio(db, portfolio)
    state = autonomous_control_service.get_or_create_state(db, settings)

    intraday_portfolio = get_or_create_portfolio(db, settings, kind=PortfolioKind.INTRADAY)
    intraday_open_position_count = _open_position_count(db, intraday_portfolio.id)
    recalculate_portfolio(db, intraday_portfolio)
    intraday_state = intraday_control_service.get_or_create_state(db, settings)

    log_event(
        db, SystemEventLevel.INFO, "startup",
        (
            f"Backend started. Daily autonomous state: {state.state.value} "
            f"({open_position_count} open positions). Intraday autonomous state: "
            f"{intraday_state.state.value} ({intraday_open_position_count} open positions). "
            "Both portfolios recalculated from existing data — no trades executed and no prior "
            "signals re-processed during recovery."
        ),
    )
    db.commit()

    return {
        "autonomous_state": state.state,
        "open_position_count": open_position_count,
        "portfolio_equity": portfolio.current_equity,
        "intraday_autonomous_state": intraday_state.state,
        "intraday_open_position_count": intraday_open_position_count,
        "intraday_portfolio_equity": intraday_portfolio.current_equity,
    }
