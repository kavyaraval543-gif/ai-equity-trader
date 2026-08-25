"""Persisted autonomous-trading state (RUNNING/PAUSED/STOPPED/ERROR).

Stored in the database (not just in memory) so it survives backend
restarts — see the Phase 3 restart-recovery requirements. Fresh installs
start STOPPED regardless of AUTONOMOUS_TRADING_ENABLED unless that setting
is explicitly true, and even then an explicit start is what actually seeds
the row; this service never silently flips state on its own.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.autonomous_state import AutonomousState
from app.models.enums import AutonomousTradingState, SystemEventLevel
from app.services.event_logger import log_event


def get_or_create_state(db: Session, settings: Settings | None = None) -> AutonomousState:
    settings = settings or get_settings()
    state = db.execute(select(AutonomousState).order_by(AutonomousState.id.asc())).scalars().first()
    if state is not None:
        return state

    initial = AutonomousTradingState.RUNNING if settings.autonomous_trading_enabled else AutonomousTradingState.STOPPED
    state = AutonomousState(state=initial, reason="Initial state seeded from AUTONOMOUS_TRADING_ENABLED.")
    db.add(state)
    db.flush()
    return state


def start(db: Session, settings: Settings | None = None) -> AutonomousState:
    settings = settings or get_settings()
    state = get_or_create_state(db, settings)

    if settings.emergency_stop:
        # Emergency stop overrides all autonomous controls — refuse to start.
        log_event(
            db, SystemEventLevel.WARNING, "autonomous_control",
            "Refused to start autonomous trading: emergency stop is active.",
        )
        db.commit()
        return state

    state.state = AutonomousTradingState.RUNNING
    state.reason = "Started via API."
    db.add(state)
    log_event(db, SystemEventLevel.INFO, "autonomous_control", "Autonomous trading started (state=RUNNING).")
    db.commit()
    db.refresh(state)
    return state


def pause(db: Session) -> AutonomousState:
    state = get_or_create_state(db)
    state.state = AutonomousTradingState.PAUSED
    state.reason = "Paused via API — existing positions remain monitored."
    db.add(state)
    log_event(db, SystemEventLevel.INFO, "autonomous_control", "Autonomous trading paused (state=PAUSED).")
    db.commit()
    db.refresh(state)
    return state


def stop(db: Session) -> AutonomousState:
    state = get_or_create_state(db)
    state.state = AutonomousTradingState.STOPPED
    state.reason = "Stopped via API."
    db.add(state)
    log_event(db, SystemEventLevel.INFO, "autonomous_control", "Autonomous trading stopped (state=STOPPED).")
    db.commit()
    db.refresh(state)
    return state


def mark_error(db: Session, reason: str) -> AutonomousState:
    state = get_or_create_state(db)
    state.state = AutonomousTradingState.ERROR
    state.reason = reason
    db.add(state)
    log_event(db, SystemEventLevel.ERROR, "autonomous_control", f"Autonomous trading entered ERROR state: {reason}")
    db.commit()
    db.refresh(state)
    return state
