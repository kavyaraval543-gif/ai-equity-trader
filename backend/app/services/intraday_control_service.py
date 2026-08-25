"""Persisted intraday autonomous-trading state.

Deliberately a separate table and separate service from the daily
`autonomous_control_service` — starting, pausing, or stopping the intraday
trader has no effect on the running daily SMA(10/30) trader, and vice
versa. Fresh installs start STOPPED; nothing in this system auto-enables it.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import AutonomousTradingState, SystemEventLevel
from app.models.intraday_state import IntradayAutonomousState
from app.services.event_logger import log_event


def get_or_create_state(db: Session, settings: Settings | None = None) -> IntradayAutonomousState:
    settings = settings or get_settings()
    state = db.execute(
        select(IntradayAutonomousState).order_by(IntradayAutonomousState.id.asc())
    ).scalars().first()
    if state is not None:
        return state

    initial = (
        AutonomousTradingState.RUNNING
        if settings.intraday_autonomous_trading_enabled
        else AutonomousTradingState.STOPPED
    )
    state = IntradayAutonomousState(
        state=initial, reason="Initial state seeded from INTRADAY_AUTONOMOUS_TRADING_ENABLED."
    )
    db.add(state)
    db.flush()
    return state


def start(db: Session, settings: Settings | None = None) -> IntradayAutonomousState:
    settings = settings or get_settings()
    state = get_or_create_state(db, settings)

    if settings.emergency_stop:
        log_event(
            db, SystemEventLevel.WARNING, "intraday_control",
            "Refused to start intraday trading: emergency stop is active.",
        )
        db.commit()
        return state

    state.state = AutonomousTradingState.RUNNING
    state.reason = "Started via API."
    db.add(state)
    log_event(db, SystemEventLevel.INFO, "intraday_control", "Intraday autonomous trading started (state=RUNNING).")
    db.commit()
    db.refresh(state)
    return state


def pause(db: Session) -> IntradayAutonomousState:
    state = get_or_create_state(db)
    state.state = AutonomousTradingState.PAUSED
    state.reason = "Paused via API — existing intraday positions remain monitored."
    db.add(state)
    log_event(db, SystemEventLevel.INFO, "intraday_control", "Intraday autonomous trading paused (state=PAUSED).")
    db.commit()
    db.refresh(state)
    return state


def stop(db: Session) -> IntradayAutonomousState:
    state = get_or_create_state(db)
    state.state = AutonomousTradingState.STOPPED
    state.reason = "Stopped via API."
    db.add(state)
    log_event(db, SystemEventLevel.INFO, "intraday_control", "Intraday autonomous trading stopped (state=STOPPED).")
    db.commit()
    db.refresh(state)
    return state


def mark_error(db: Session, reason: str) -> IntradayAutonomousState:
    state = get_or_create_state(db)
    state.state = AutonomousTradingState.ERROR
    state.reason = reason
    db.add(state)
    log_event(db, SystemEventLevel.ERROR, "intraday_control", f"Intraday trading entered ERROR state: {reason}")
    db.commit()
    db.refresh(state)
    return state
