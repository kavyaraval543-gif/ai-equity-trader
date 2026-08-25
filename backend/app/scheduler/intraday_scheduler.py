"""Background scheduler for autonomous intraday paper trading.

Mirrors `app/scheduler/trading_scheduler.py`'s `TradingScheduler` exactly in
shape — two independent daemon-thread loops, a `threading.Event` for
cancellation, no third-party scheduling library — but is a wholly separate
instance, gated by its own `IntradayAutonomousState`, running its own
intervals, and touching only the INTRADAY portfolio:

  - entry loop: checks the market session, the intraday autonomous state,
    AND (unlike the daily loop) whether we are within
    `intraday_no_entry_minutes_before_close` minutes of session end — if all
    clear, runs a guarded intraday cycle to look for new entries.
  - monitor loop: always runs (existing intraday positions must be
    monitored independently of whether new entries are paused/stopped),
    checking exit rules — including the intraday-only max-holding-time and
    force-close-at-session-end rules — for every open intraday position.

This scheduler defaults to doing nothing: `IntradayAutonomousState` is
seeded STOPPED unless `INTRADAY_AUTONOMOUS_TRADING_ENABLED=true` is set, so
starting this scheduler (which happens automatically at app startup, same
as the daily one) does not by itself cause any intraday trade to be placed.
The daily SMA(10/30) `TradingScheduler` is untouched by this file.
"""
import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.database.session import SessionLocal
from app.models.enums import AutonomousTradingState, SystemEventLevel
from app.risk.intraday_rules import is_near_session_end
from app.scheduler.runners import run_guarded_intraday_cycle, run_guarded_intraday_position_monitor
from app.services import intraday_control_service
from app.services.event_logger import log_event
from app.services.market_session_service import MarketSessionService

logger = logging.getLogger("intraday_scheduler")


class IntradayScheduler:
    def __init__(
        self,
        settings: Settings | None = None,
        session_factory: Callable[[], Session] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
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
                logger.warning("IntradayScheduler.start() called while already running — ignoring.")
                return
            self._stop_event.clear()
            self._entry_thread = threading.Thread(
                target=self._entry_loop, daemon=True, name="intraday-entry-scheduler"
            )
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop, daemon=True, name="intraday-position-monitor-scheduler"
            )
            self._entry_thread.start()
            self._monitor_thread.start()
            self._started = True

        db = self._session_factory()
        try:
            log_event(
                db, SystemEventLevel.INFO, "intraday_scheduler",
                f"Intraday scheduler started (entry cycle every "
                f"{self.settings.intraday_cycle_interval_seconds}s, position monitor every "
                f"{self.settings.intraday_position_monitor_interval_seconds}s). "
                f"Autonomous intraday trading state is independent and defaults to STOPPED.",
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
            log_event(db, SystemEventLevel.INFO, "intraday_scheduler", "Intraday scheduler stopped.")
            db.commit()
        finally:
            db.close()

    # --- entry loop ---

    def _entry_loop(self) -> None:
        while not self._stop_event.is_set():
            self._entry_tick()
            self._stop_event.wait(self.settings.intraday_cycle_interval_seconds)

    def _entry_tick(self) -> None:
        db = self._session_factory()
        try:
            state = intraday_control_service.get_or_create_state(db, self.settings)
            db.commit()

            if self.settings.emergency_stop:
                self.last_skip_reason = "Emergency stop is active."
                return
            if state.state != AutonomousTradingState.RUNNING:
                self.last_skip_reason = f"Intraday autonomous state is {state.state.value}, not RUNNING."
                return

            market_session = MarketSessionService(self.settings)
            status = market_session.get_status()
            if not market_session.is_open():
                self.last_skip_reason = f"Market session is {status.value}."
                return

            now_ist = market_session.now()
            if is_near_session_end(
                now_ist, self.settings.market_session_end, self.settings.intraday_no_entry_minutes_before_close
            ):
                self.last_skip_reason = (
                    f"Within {self.settings.intraday_no_entry_minutes_before_close} minutes of session end — "
                    "no new intraday entries."
                )
                return

            self.last_skip_reason = None
            outcome = run_guarded_intraday_cycle(db)
            if not outcome.ran:
                self.last_skip_reason = outcome.skipped_reason
                return

            self.last_successful_cycle_at = datetime.now(timezone.utc)
            self.last_error = None
        except Exception as exc:  # noqa: BLE001 — one bad cycle must not kill the loop
            self.last_failed_cycle_at = datetime.now(timezone.utc)
            self.last_error = str(exc)
            logger.exception("Scheduled intraday entry cycle failed")
            try:
                db.rollback()
                log_event(db, SystemEventLevel.ERROR, "intraday_scheduler", f"Scheduled intraday cycle failed: {exc}")
                db.commit()
            except Exception:  # noqa: BLE001 — logging the failure must not itself raise
                logger.exception("Failed to log intraday scheduler failure")
        finally:
            db.close()

    # --- position monitor loop ---

    def _monitor_loop(self) -> None:
        while not self._stop_event.is_set():
            self._monitor_tick()
            self._stop_event.wait(self.settings.intraday_position_monitor_interval_seconds)

    def _monitor_tick(self) -> None:
        db = self._session_factory()
        try:
            outcome = run_guarded_intraday_position_monitor(db)
            self.last_monitor_run_at = datetime.now(timezone.utc)
            if outcome.ran:
                self.last_monitor_error = None
        except Exception as exc:  # noqa: BLE001 — one bad pass must not kill the loop
            self.last_monitor_error = str(exc)
            logger.exception("Intraday position monitor pass failed")
            try:
                db.rollback()
                log_event(
                    db, SystemEventLevel.ERROR, "intraday_scheduler", f"Intraday position monitor pass failed: {exc}"
                )
                db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to log intraday position monitor failure")
        finally:
            db.close()


intraday_scheduler = IntradayScheduler()
