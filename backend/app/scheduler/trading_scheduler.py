"""Background scheduler for autonomous paper trading.

Two independent periodic loops, each a daemon thread with its own
configurable interval:

  - entry loop: checks the market session + autonomous state, then (only if
    both allow it) runs a guarded trading cycle to look for new entries.
  - monitor loop: always runs (existing positions must be monitored
    independently of whether new entries are paused/stopped), checking
    exit rules for every open position.

Implemented with plain `threading.Thread` + a `threading.Event` for
cancellation rather than a third-party scheduling library — the rest of
this codebase is synchronous SQLAlchemy, so a simple, transparent loop is a
better fit than mixing in asyncio or a new dependency. The stop event makes
this a controlled, cancellable loop rather than an uncontrolled one.

A single `TradingScheduler` instance is created per process; `start()` is a
no-op (with a logged warning) if called while already running, which is
this process's guard against accidentally starting a second copy of the
scheduler. Cross-process duplicate *execution* is separately guarded by the
Postgres advisory lock in app/scheduler/guards.py.
"""
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import SessionLocal
from app.models.enums import AutonomousTradingState, SystemEventLevel
from app.scheduler.runners import run_guarded_entry_cycle, run_guarded_position_monitor
from app.services import autonomous_control_service
from app.services.event_logger import log_event
from app.services.market_session_service import MarketSessionService

logger = logging.getLogger("trading_scheduler")


class TradingScheduler:
    def __init__(
        self,
        settings: Settings | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        # Injectable for tests (e.g. an isolated SQLite sessionmaker); the
        # running application always uses the real SessionLocal.
        self._session_factory = session_factory or SessionLocal
        self._stop_event = threading.Event()
        self._entry_thread: threading.Thread | None = None
        self._monitor_thread: threading.Thread | None = None
        self._start_lock = threading.Lock()
        self._started = False

        self.last_successful_cycle_at: datetime | None = None
        self.last_failed_cycle_at: datetime | None = None
        self.last_error: str | None = None
        self.last_skip_reason: str | None = None
        self.last_monitor_run_at: datetime | None = None
        self.last_monitor_error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._started

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                logger.warning("TradingScheduler.start() called while already running — ignoring.")
                return
            self._stop_event.clear()
            self._entry_thread = threading.Thread(target=self._entry_loop, daemon=True, name="entry-scheduler")
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True, name="position-monitor-scheduler"
            )
            self._entry_thread.start()
            self._monitor_thread.start()
            self._started = True

        db = self._session_factory()
        try:
            log_event(
                db, SystemEventLevel.INFO, "scheduler",
                f"Scheduler started (entry cycle every {self.settings.trading_cycle_interval_seconds}s, "
                f"position monitor every {self.settings.position_monitor_interval_seconds}s).",
            )
            db.commit()
        finally:
            db.close()

    def shutdown(self, timeout: float = 10.0) -> None:
        with self._start_lock:
            if not self._started:
                return
            self._stop_event.set()

        for t in (self._entry_thread, self._monitor_thread):
            if t is not None:
                t.join(timeout=timeout)

        with self._start_lock:
            self._started = False

        db = self._session_factory()
        try:
            log_event(db, SystemEventLevel.INFO, "scheduler", "Scheduler stopped.")
            db.commit()
        finally:
            db.close()

    # --- entry loop ---

    def _entry_loop(self) -> None:
        while not self._stop_event.is_set():
            self._entry_tick()
            self._stop_event.wait(self.settings.trading_cycle_interval_seconds)

    def _entry_tick(self) -> None:
        db = self._session_factory()
        try:
            state = autonomous_control_service.get_or_create_state(db, self.settings)
            db.commit()

            if self.settings.emergency_stop:
                self.last_skip_reason = "Emergency stop is active."
                return
            if state.state != AutonomousTradingState.RUNNING:
                self.last_skip_reason = f"Autonomous state is {state.state.value}, not RUNNING."
                return

            market_session = MarketSessionService(self.settings)
            status = market_session.get_status()
            if not market_session.is_open():
                self.last_skip_reason = f"Market session is {status.value}."
                return

            self.last_skip_reason = None
            outcome = run_guarded_entry_cycle(db)
            if not outcome.ran:
                self.last_skip_reason = outcome.skipped_reason
                return

            self.last_successful_cycle_at = datetime.now(timezone.utc)
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 — one bad cycle must not kill the loop
            self.last_failed_cycle_at = datetime.now(timezone.utc)
            self.last_error = str(exc)
            logger.exception("Scheduled entry cycle failed")
            try:
                db.rollback()
                log_event(db, SystemEventLevel.ERROR, "scheduler", f"Scheduled entry cycle failed: {exc}")
                db.commit()
            except Exception:  # noqa: BLE001 — logging the failure must not itself raise
                logger.exception("Failed to log scheduler failure")
        finally:
            db.close()

    # --- position monitor loop ---

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            self._monitor_tick()
            self._stop_event.wait(self.settings.position_monitor_interval_seconds)

    def _monitor_tick(self) -> None:
        db = self._session_factory()
        try:
            outcome = run_guarded_position_monitor(db)
            self.last_monitor_run_at = datetime.now(timezone.utc)
            if outcome.ran:
                self.last_monitor_error = None
        except Exception as exc:  # noqa: BLE001 — one bad pass must not kill the loop
            self.last_monitor_error = str(exc)
            logger.exception("Position monitor pass failed")
            try:
                db.rollback()
                log_event(db, SystemEventLevel.ERROR, "scheduler", f"Position monitor pass failed: {exc}")
                db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to log position monitor failure")
        finally:
            db.close()


scheduler = TradingScheduler()
