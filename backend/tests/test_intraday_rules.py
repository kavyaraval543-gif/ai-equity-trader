"""Pure-function tests for app/risk/intraday_rules.py — the shared rule
logic used by both the live IntradayRiskEngine and the IntradayBacktestEngine.
Testing them here once, directly, is what guarantees both call sites stay
correct without re-deriving the same edge cases twice."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.risk import intraday_rules

IST = ZoneInfo("Asia/Kolkata")


def test_max_consecutive_losses_reached_at_threshold():
    assert intraday_rules.is_max_consecutive_losses_reached(3, 3) is True
    assert intraday_rules.is_max_consecutive_losses_reached(2, 3) is False


def test_cooldown_active_within_window():
    now = datetime(2026, 1, 5, 10, 0, tzinfo=IST)
    last_loss = now - timedelta(minutes=5)
    assert intraday_rules.is_in_cooldown(now, last_loss, cooldown_minutes=15) is True


def test_cooldown_expired_after_window():
    now = datetime(2026, 1, 5, 10, 0, tzinfo=IST)
    last_loss = now - timedelta(minutes=20)
    assert intraday_rules.is_in_cooldown(now, last_loss, cooldown_minutes=15) is False


def test_cooldown_disabled_when_zero_minutes():
    now = datetime(2026, 1, 5, 10, 0, tzinfo=IST)
    last_loss = now - timedelta(seconds=1)
    assert intraday_rules.is_in_cooldown(now, last_loss, cooldown_minutes=0) is False


def test_cooldown_false_when_no_prior_loss():
    now = datetime(2026, 1, 5, 10, 0, tzinfo=IST)
    assert intraday_rules.is_in_cooldown(now, None, cooldown_minutes=15) is False


def test_near_session_end_true_within_cutoff():
    session_end = "15:30"
    at_1520 = datetime(2026, 1, 5, 15, 20, tzinfo=IST)  # 10 min before close
    assert intraday_rules.is_near_session_end(at_1520, session_end, minutes_before_close=15) is True


def test_near_session_end_false_outside_cutoff():
    session_end = "15:30"
    at_1400 = datetime(2026, 1, 5, 14, 0, tzinfo=IST)
    assert intraday_rules.is_near_session_end(at_1400, session_end, minutes_before_close=15) is False


def test_near_session_end_true_past_close():
    session_end = "15:30"
    at_1535 = datetime(2026, 1, 5, 15, 35, tzinfo=IST)
    assert intraday_rules.is_near_session_end(at_1535, session_end, minutes_before_close=15) is True


def test_max_trades_per_day_reached_at_threshold():
    assert intraday_rules.is_max_trades_per_day_reached(5, 5) is True
    assert intraday_rules.is_max_trades_per_day_reached(4, 5) is False


def test_daily_loss_limit_reached():
    # 2% of 100,000 = 2,000 max loss.
    assert intraday_rules.is_daily_loss_limit_reached(-2000.0, 100_000.0, 0.02) is True
    assert intraday_rules.is_daily_loss_limit_reached(-1999.0, 100_000.0, 0.02) is False
    # Positive P&L never trips the limit.
    assert intraday_rules.is_daily_loss_limit_reached(500.0, 100_000.0, 0.02) is False


def test_max_holding_time_exceeded():
    opened = datetime(2026, 1, 5, 10, 0, tzinfo=IST)
    still_holding = opened + timedelta(minutes=119)
    exceeded = opened + timedelta(minutes=120)
    assert intraday_rules.has_exceeded_max_holding_time(opened, still_holding, 120) is False
    assert intraday_rules.has_exceeded_max_holding_time(opened, exceeded, 120) is True


def test_max_holding_time_disabled_when_zero():
    opened = datetime(2026, 1, 5, 10, 0, tzinfo=IST)
    far_future = opened + timedelta(days=10)
    assert intraday_rules.has_exceeded_max_holding_time(opened, far_future, 0) is False
