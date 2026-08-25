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
from app.models.enums import PositionStatus, SystemEventLevel
from app.models.position import Position
from app.services import autonomous_control_service
from app.services.event_logger import log_event
from app.services.portfolio_service import get_or_create_portfolio, recalculate_portfolio


def run_startup_recovery(db: Session, settings: Settings | None = None) -> dict:
    settings = settings or get_settings()

    portfolio = get_or_create_portfolio(db, settings)
    open_position_count = db.execute(
        select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
    ).scalar_one()

    # Refresh equity from positions' last-known prices already in the DB;
    # the position monitor's next tick will fetch fresh real prices shortly.
    recalculate_portfolio(db, portfolio)

    state = autonomous_control_service.get_or_create_state(db, settings)

    log_event(
        db, SystemEventLevel.INFO, "startup",
        (
            f"Backend started. Autonomous state: {state.state.value}. "
            f"Open positions: {open_position_count}. Portfolio recalculated from existing data — "
            "no trades executed and no prior signals re-processed during recovery."
        ),
    )
    db.commit()

    return {
        "autonomous_state": state.state,
        "open_position_count": open_position_count,
        "portfolio_equity": portfolio.current_equity,
    }
