"""Duplicate/overlap protection tests.

Only the skip path of run_guarded_*() is exercised here — the "acquired and
actually runs" path would invoke the real orchestrator/monitor (network
calls, Postgres-specific upsert SQL), which is already covered by the
dedicated orchestrator/position-monitor/end-to-end tests. This file is
purely about the locking mechanics.
"""
import pytest

from app.scheduler.guards import (
    ENTRY_CYCLE_LOCK_KEY,
    POSITION_MONITOR_LOCK_KEY,
    CycleGuard,
    cycle_guard,
    entry_cycle_guard,
    position_monitor_guard,
)
from app.scheduler.runners import run_guarded_entry_cycle, run_guarded_position_monitor


@pytest.fixture(autouse=True)
def _reset_module_guards():
    """entry_cycle_guard/position_monitor_guard are process-wide singletons —
    make sure a failed test can't leave them locked for the next one."""
    yield
    if entry_cycle_guard._lock.locked():
        entry_cycle_guard.release()
    if position_monitor_guard._lock.locked():
        position_monitor_guard.release()


def test_cycle_guard_acquire_and_release():
    guard = CycleGuard("test")

    assert guard.try_acquire() is True
    assert guard.try_acquire() is False  # already held
    guard.release()
    assert guard.try_acquire() is True  # available again
    guard.release()


def test_cycle_guard_context_manager_skips_when_held(db_session):
    guard = CycleGuard("test")
    guard.try_acquire()  # simulate another cycle already running

    with cycle_guard(db_session, guard, 999_999) as acquired:
        assert acquired is False

    guard.release()


def test_cycle_guard_context_manager_acquires_when_free(db_session):
    guard = CycleGuard("test")

    with cycle_guard(db_session, guard, 999_998) as acquired:
        assert acquired is True
        assert guard.try_acquire() is False  # held for the duration of the block

    assert guard.try_acquire() is True  # released on exit
    guard.release()


def test_run_guarded_entry_cycle_skips_when_already_running(db_session):
    entry_cycle_guard.try_acquire()  # simulate a scheduled cycle already in flight

    outcome = run_guarded_entry_cycle(db_session)

    assert outcome.ran is False
    assert "already running" in outcome.skipped_reason


def test_run_guarded_position_monitor_skips_when_already_running(db_session):
    position_monitor_guard.try_acquire()

    outcome = run_guarded_position_monitor(db_session)

    assert outcome.ran is False
    assert "already running" in outcome.skipped_reason


def test_entry_and_monitor_guards_are_independent(db_session):
    """Holding the entry-cycle guard must not block the position monitor,
    and vice versa — they are required to run independently."""
    entry_cycle_guard.try_acquire()

    with cycle_guard(db_session, position_monitor_guard, POSITION_MONITOR_LOCK_KEY) as acquired:
        assert acquired is True


def test_lock_keys_are_distinct():
    assert ENTRY_CYCLE_LOCK_KEY != POSITION_MONITOR_LOCK_KEY
