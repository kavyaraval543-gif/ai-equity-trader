"""Overlap/duplicate-execution protection for trading cycles and position
monitor passes.

Chosen approach (two layers, both must be acquired):

1. An in-process, non-blocking `threading.Lock` per cycle type. This is the
   primary guard and covers the common case: a manual POST /run-cycle and
   the scheduler's own tick sharing the *same* lock object, so they cannot
   run concurrently within one backend process. Non-blocking: if the lock is
   held, the caller is told to skip immediately rather than queueing up.

2. A Postgres advisory lock (`pg_try_advisory_lock`), taken only after the
   in-process lock succeeds. This is defense-in-depth against running more
   than one backend process (e.g. `uvicorn --workers 2`, or two instances
   during a deploy) — advisory locks are visible across connections/
   processes but auto-release if a session dies, so a crashed process can
   never leave a stale lock behind. It's a no-op (always "acquired") on
   non-Postgres test databases, so the in-process lock remains the layer
   exercised in unit tests.

Position monitoring and new-entry scanning use separate guards/keys, since
they are required to run independently of each other.
"""
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

# Arbitrary fixed keys, one per cycle type, for the Postgres advisory lock.
# The intraday keys are distinct from the daily ones so the two traders never
# block each other — they are independent systems on separate portfolios.
ENTRY_CYCLE_LOCK_KEY = 918_273_001
POSITION_MONITOR_LOCK_KEY = 918_273_002
INTRADAY_ENTRY_CYCLE_LOCK_KEY = 918_273_003
INTRADAY_POSITION_MONITOR_LOCK_KEY = 918_273_004


class CycleGuard:
    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        return self._lock.acquire(blocking=False)

    def release(self) -> None:
        self._lock.release()


entry_cycle_guard = CycleGuard("entry_cycle")
position_monitor_guard = CycleGuard("position_monitor")
intraday_entry_cycle_guard = CycleGuard("intraday_entry_cycle")
intraday_position_monitor_guard = CycleGuard("intraday_position_monitor")


def _try_pg_advisory_lock(db: Session, key: int) -> bool:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return True  # no-op on non-Postgres (e.g. SQLite in tests)
    return bool(db.execute(select_pg_try_advisory_lock(key)).scalar())


def _pg_advisory_unlock(db: Session, key: int) -> None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return
    db.execute(select_pg_advisory_unlock(key))


def select_pg_try_advisory_lock(key: int):
    from sqlalchemy import func

    return select(func.pg_try_advisory_lock(key))


def select_pg_advisory_unlock(key: int):
    from sqlalchemy import func

    return select(func.pg_advisory_unlock(key))


@contextmanager
def cycle_guard(db: Session, guard: CycleGuard, pg_key: int) -> Iterator[bool]:
    """Yields True if the cycle may proceed, False if another instance
    (in-process or cross-process) already holds it — caller should skip."""
    acquired_local = guard.try_acquire()
    if not acquired_local:
        yield False
        return

    acquired_pg = _try_pg_advisory_lock(db, pg_key)
    if not acquired_pg:
        guard.release()
        yield False
        return

    try:
        yield True
    finally:
        _pg_advisory_unlock(db, pg_key)
        guard.release()
