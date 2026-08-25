from datetime import datetime

from pydantic import BaseModel

from app.models.enums import AutonomousTradingState


class AutonomousStatusOut(BaseModel):
    state: AutonomousTradingState
    reason: str | None
    updated_at: datetime
    emergency_stop: bool
    scheduler_running: bool
    trading_cycle_interval_seconds: int
    position_monitor_interval_seconds: int
    last_successful_cycle_at: datetime | None
    last_failed_cycle_at: datetime | None
    last_error: str | None
    last_skip_reason: str | None
    last_monitor_run_at: datetime | None
    last_monitor_error: str | None
    open_position_count: int
