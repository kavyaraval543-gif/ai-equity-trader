"""Pure, side-effect-free intraday risk rule checks.

These are shared verbatim by both `IntradayRiskEngine` (the live paper
trading path, layered on top of — never bypassing — the base RiskEngine)
and `IntradayBacktestEngine` (which has no live Portfolio/DB to call the
risk engine against, but must enforce identical rules). Keeping the rule
logic here as plain functions means both places can never drift apart.
"""
from datetime import datetime, time, timedelta


def is_max_consecutive_losses_reached(consecutive_losses: int, max_allowed: int) -> bool:
    return consecutive_losses >= max_allowed


def is_in_cooldown(current_time: datetime, last_loss_at: datetime | None, cooldown_minutes: int) -> bool:
    if last_loss_at is None or cooldown_minutes <= 0:
        return False
    return current_time < last_loss_at + timedelta(minutes=cooldown_minutes)


def is_near_session_end(current_time: datetime, session_end: str, minutes_before_close: int) -> bool:
    """`session_end` is "HH:MM" (e.g. "15:30"). True once `current_time` is
    within `minutes_before_close` minutes of that time (or past it)."""
    end_hour, end_minute = (int(x) for x in session_end.split(":"))
    cutoff = (
        datetime.combine(current_time.date(), time(end_hour, end_minute), tzinfo=current_time.tzinfo)
        - timedelta(minutes=minutes_before_close)
    )
    return current_time >= cutoff


def is_max_trades_per_day_reached(trades_today: int, max_allowed: int) -> bool:
    return trades_today >= max_allowed


def is_daily_loss_limit_reached(realized_pnl_today: float, starting_capital: float, max_daily_loss_pct: float) -> bool:
    max_daily_loss = max_daily_loss_pct * starting_capital
    return realized_pnl_today <= -max_daily_loss


def has_exceeded_max_holding_time(opened_at: datetime, current_time: datetime, max_holding_minutes: int) -> bool:
    if max_holding_minutes <= 0:
        return False
    return current_time >= opened_at + timedelta(minutes=max_holding_minutes)
