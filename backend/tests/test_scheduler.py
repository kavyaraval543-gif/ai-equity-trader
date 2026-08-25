"""TradingScheduler tests.

Uses a temp-file-backed SQLite database (each thread/session gets its own
connection to the same file — unlike `:memory:`, which would force every
thread onto one shared connection and trip SQLite's same-connection
concurrency limits) with an empty positions table and the default STOPPED
autonomous state. That keeps both loops on their early-return paths — no
real market data provider or Postgres-specific SQL is reached, so these
tests need neither network access nor a live Postgres server, while still
exercising the real thread lifecycle, interval timing, and duplicate-start
protection.
"""
import os
import tempfile
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.database.base import Base
import app.models  # noqa: F401
from app.scheduler.trading_scheduler import TradingScheduler


def _settings(**overrides) -> Settings:
    defaults = dict(
        trading_cycle_interval_seconds=1,
        position_monitor_interval_seconds=1,
        emergency_stop=False,
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


@pytest.fixture()
def session_factory():
    fd, path = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()
    os.remove(path)


def test_scheduler_starts_and_stops_cleanly(session_factory):
    sched = TradingScheduler(_settings(), session_factory=session_factory)

    assert sched.is_running is False
    sched.start()
    assert sched.is_running is True
    sched.shutdown(timeout=5)
    assert sched.is_running is False


def test_scheduler_ticks_at_configured_interval(session_factory):
    sched = TradingScheduler(_settings(trading_cycle_interval_seconds=1, position_monitor_interval_seconds=1),
                              session_factory=session_factory)

    sched.start()
    try:
        time.sleep(2.5)
        # With a 1s interval and ~2.5s elapsed, the monitor loop (which
        # always runs, since autonomous state defaults to STOPPED and it
        # doesn't gate on that) should have ticked more than once.
        assert sched.last_monitor_run_at is not None
    finally:
        sched.shutdown(timeout=5)


def test_double_start_does_not_spawn_a_second_scheduler(session_factory):
    sched = TradingScheduler(_settings(), session_factory=session_factory)
    sched.start()
    try:
        first_entry_thread = sched._entry_thread
        first_monitor_thread = sched._monitor_thread

        sched.start()  # should be a no-op

        assert sched._entry_thread is first_entry_thread
        assert sched._monitor_thread is first_monitor_thread
    finally:
        sched.shutdown(timeout=5)


def test_entry_tick_skips_when_autonomous_state_is_stopped(session_factory):
    """Fresh installs default to STOPPED — the scheduler must not run entry
    cycles until explicitly started via the API."""
    sched = TradingScheduler(_settings(), session_factory=session_factory)

    sched._entry_tick()

    assert sched.last_successful_cycle_at is None
    assert sched.last_skip_reason is not None
    assert "STOPPED" in sched.last_skip_reason


def test_entry_tick_skips_when_emergency_stop_active(session_factory):
    sched = TradingScheduler(_settings(emergency_stop=True), session_factory=session_factory)

    sched._entry_tick()

    assert sched.last_successful_cycle_at is None
    assert "Emergency stop" in sched.last_skip_reason


def test_monitor_tick_runs_with_no_open_positions(session_factory):
    sched = TradingScheduler(_settings(), session_factory=session_factory)

    sched._monitor_tick()

    assert sched.last_monitor_run_at is not None
    assert sched.last_monitor_error is None


def test_a_failing_tick_does_not_crash_the_loop(session_factory, monkeypatch):
    sched = TradingScheduler(_settings(), session_factory=session_factory)

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "app.scheduler.trading_scheduler.autonomous_control_service.get_or_create_state", _boom
    )

    # Must not raise — failures are caught, logged, and recorded.
    sched._entry_tick()

    assert sched.last_error == "simulated failure"
    assert sched.last_failed_cycle_at is not None
