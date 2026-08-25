"""Guarded entrypoints for running a trading cycle or a position-monitor
pass. Both the manual API endpoint and the autonomous scheduler call these
same functions — so "manual and scheduled cycles must use the same trading
orchestrator" and "cannot duplicate execution" are satisfied by construction,
not by convention.
"""
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models.enums import SystemEventLevel
from app.scheduler.guards import (
    ENTRY_CYCLE_LOCK_KEY,
    POSITION_MONITOR_LOCK_KEY,
    cycle_guard,
    entry_cycle_guard,
    position_monitor_guard,
)
from app.services.event_logger import log_event
from app.services.position_monitor import PositionMonitor
from app.services.trading_orchestrator import TradingOrchestrator


@dataclass
class GuardedRunOutcome:
    ran: bool
    result: Any | None
    skipped_reason: str | None = None


def run_guarded_entry_cycle(db: Session) -> GuardedRunOutcome:
    with cycle_guard(db, entry_cycle_guard, ENTRY_CYCLE_LOCK_KEY) as acquired:
        if not acquired:
            log_event(
                db, SystemEventLevel.WARNING, "scheduler",
                "Entry cycle skipped: another entry cycle (manual or scheduled) is already running.",
            )
            db.commit()
            return GuardedRunOutcome(ran=False, result=None, skipped_reason="A trading cycle is already running.")

        orchestrator = TradingOrchestrator(db)
        result = orchestrator.run_cycle()
        return GuardedRunOutcome(ran=True, result=result)


def run_guarded_position_monitor(db: Session) -> GuardedRunOutcome:
    with cycle_guard(db, position_monitor_guard, POSITION_MONITOR_LOCK_KEY) as acquired:
        if not acquired:
            log_event(
                db, SystemEventLevel.WARNING, "scheduler", "Position monitor pass skipped: already running."
            )
            db.commit()
            return GuardedRunOutcome(
                ran=False, result=None, skipped_reason="A position monitor pass is already running."
            )

        monitor = PositionMonitor(db)
        result = monitor.run()
        return GuardedRunOutcome(ran=True, result=result)
