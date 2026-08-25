"""Health and system-status endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import get_db
from app.models.enums import PositionStatus
from app.models.position import Position
from app.models.system_event import SystemEvent
from app.scheduler.trading_scheduler import scheduler
from app.schemas.system_event import SystemEventOut
from app.services import autonomous_control_service
from app.services.market_session_service import MarketSessionService

router = APIRouter(tags=["system"])


@router.get("/health")
def health() -> dict:
    """Liveness check — does not touch the database."""
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/system/status")
def system_status(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Readiness check — backend, database, scheduler, autonomous trading,
    market session, and position monitor status."""
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — surface any DB failure as a status field
        db_status = f"error: {exc}"

    market_session = MarketSessionService(settings).describe()

    autonomous_state = None
    open_position_count = None
    if db_status == "ok":
        try:
            state = autonomous_control_service.get_or_create_state(db, settings)
            db.commit()
            autonomous_state = state.state.value
            open_position_count = db.execute(
                select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
            ).scalar_one()
        except Exception as exc:  # noqa: BLE001 — DB flaked mid-query; report it, don't crash the endpoint
            db_status = f"error: {exc}"

    return {
        "backend": "ok",
        "database": db_status,
        "trading_mode": settings.trading_mode,
        "emergency_stop": settings.emergency_stop,
        "market_data_provider": settings.market_data_provider,
        "environment": settings.environment,
        "scheduler": {
            "running": scheduler.is_running,
            "trading_cycle_interval_seconds": settings.trading_cycle_interval_seconds,
            "position_monitor_interval_seconds": settings.position_monitor_interval_seconds,
            "last_successful_cycle_at": scheduler.last_successful_cycle_at,
            "last_failed_cycle_at": scheduler.last_failed_cycle_at,
            "last_error": scheduler.last_error,
            "last_skip_reason": scheduler.last_skip_reason,
        },
        "position_monitor": {
            "last_run_at": scheduler.last_monitor_run_at,
            "last_error": scheduler.last_monitor_error,
        },
        "autonomous_state": autonomous_state,
        "market_session": market_session,
        "open_position_count": open_position_count,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/system/events", response_model=list[SystemEventOut])
def get_system_events(db: Session = Depends(get_db), limit: int = Query(50, ge=1, le=500)) -> list[SystemEventOut]:
    events = db.execute(select(SystemEvent).order_by(SystemEvent.timestamp.desc()).limit(limit)).scalars().all()
    return [SystemEventOut.model_validate(e) for e in events]
