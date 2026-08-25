"""Guarded entrypoints for running a trading cycle or a position-monitor
pass. Both the manual API endpoint and the autonomous scheduler call these
same functions — so "manual and scheduled cycles must use the same trading
orchestrator" and "cannot duplicate execution" are satisfied by construction,
not by convention.
"""
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.execution.paper import PaperExecutionProvider
from app.models.enums import PortfolioKind, SystemEventLevel
from app.risk.intraday_engine import IntradayRiskEngine
from app.scheduler.guards import (
    ENTRY_CYCLE_LOCK_KEY,
    INTRADAY_ENTRY_CYCLE_LOCK_KEY,
    INTRADAY_POSITION_MONITOR_LOCK_KEY,
    POSITION_MONITOR_LOCK_KEY,
    cycle_guard,
    entry_cycle_guard,
    intraday_entry_cycle_guard,
    intraday_position_monitor_guard,
    position_monitor_guard,
)
from app.services.event_logger import log_event
from app.services.intraday_orchestrator import IntradayOrchestrator
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


def run_guarded_intraday_cycle(db: Session) -> GuardedRunOutcome:
    with cycle_guard(db, intraday_entry_cycle_guard, INTRADAY_ENTRY_CYCLE_LOCK_KEY) as acquired:
        if not acquired:
            log_event(
                db, SystemEventLevel.WARNING, "intraday_scheduler",
                "Intraday cycle skipped: another intraday cycle (manual or scheduled) is already running.",
            )
            db.commit()
            return GuardedRunOutcome(
                ran=False, result=None, skipped_reason="An intraday trading cycle is already running."
            )

        orchestrator = IntradayOrchestrator(db)
        result = orchestrator.run_cycle()
        return GuardedRunOutcome(ran=True, result=result)


def build_intraday_position_monitor(db: Session) -> PositionMonitor:
    """The intraday position monitor is the same PositionMonitor class,
    scoped to the INTRADAY portfolio and configured with intraday exit
    thresholds, costs, and slippage."""
    settings = get_settings()
    return PositionMonitor(
        db,
        settings=settings,
        risk_engine=IntradayRiskEngine(settings),
        execution=PaperExecutionProvider(
            settings,
            transaction_cost_percent=settings.intraday_transaction_cost_percent,
            stop_loss_percent=settings.intraday_stop_loss_percent,
            target_percent=settings.intraday_target_percent,
            slippage_percent=settings.intraday_slippage_percent,
        ),
        portfolio_kind=PortfolioKind.INTRADAY,
        trailing_stop_enabled=settings.intraday_trailing_stop_enabled,
        trailing_stop_percent=settings.intraday_trailing_stop_percent,
        force_close_at_session_end=settings.intraday_force_close_at_session_end,
        max_holding_minutes=settings.intraday_max_holding_minutes,
        monitor_label="INTRADAY_POSITION_MONITOR",
    )


def run_guarded_intraday_position_monitor(db: Session) -> GuardedRunOutcome:
    with cycle_guard(db, intraday_position_monitor_guard, INTRADAY_POSITION_MONITOR_LOCK_KEY) as acquired:
        if not acquired:
            log_event(
                db, SystemEventLevel.WARNING, "intraday_scheduler",
                "Intraday position monitor pass skipped: already running.",
            )
            db.commit()
            return GuardedRunOutcome(
                ran=False, result=None, skipped_reason="An intraday position monitor pass is already running."
            )

        result = build_intraday_position_monitor(db).run()
        return GuardedRunOutcome(ran=True, result=result)
