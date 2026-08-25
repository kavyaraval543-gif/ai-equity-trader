from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.models.enums import MarketSessionStatus
from app.services.market_session_service import MarketSessionService

IST = ZoneInfo("Asia/Kolkata")


def _service(**overrides) -> MarketSessionService:
    defaults = dict(
        market_timezone="Asia/Kolkata",
        market_session_start="09:15",
        market_session_end="15:30",
        market_holidays=["2026-01-26"],
    )
    defaults.update(overrides)
    return MarketSessionService(Settings(_env_file=None, **defaults))


def test_weekday_during_session_is_open():
    service = _service()
    monday_noon = datetime(2026, 8, 24, 12, 0, tzinfo=IST)  # a Monday

    assert service.get_status(monday_noon) == MarketSessionStatus.MARKET_OPEN
    assert service.is_open(monday_noon) is True


def test_before_session_is_pre_market():
    service = _service()
    monday_early = datetime(2026, 8, 24, 8, 0, tzinfo=IST)

    assert service.get_status(monday_early) == MarketSessionStatus.PRE_MARKET
    assert service.is_open(monday_early) is False


def test_after_session_is_after_market():
    service = _service()
    monday_evening = datetime(2026, 8, 24, 16, 0, tzinfo=IST)

    assert service.get_status(monday_evening) == MarketSessionStatus.AFTER_MARKET
    assert service.is_open(monday_evening) is False


def test_weekend_is_weekend():
    service = _service()
    saturday_noon = datetime(2026, 8, 22, 12, 0, tzinfo=IST)  # a Saturday

    assert service.get_status(saturday_noon) == MarketSessionStatus.WEEKEND
    assert service.is_open(saturday_noon) is False


def test_configured_holiday_is_holiday():
    service = _service()
    holiday_noon = datetime(2026, 1, 26, 12, 0, tzinfo=IST)  # a Monday, configured holiday

    assert service.get_status(holiday_noon) == MarketSessionStatus.HOLIDAY
    assert service.is_open(holiday_noon) is False


def test_session_boundaries_are_inclusive():
    service = _service()
    at_open = datetime(2026, 8, 24, 9, 15, tzinfo=IST)
    at_close = datetime(2026, 8, 24, 15, 30, tzinfo=IST)

    assert service.get_status(at_open) == MarketSessionStatus.MARKET_OPEN
    assert service.get_status(at_close) == MarketSessionStatus.MARKET_OPEN


def test_uses_configured_timezone_not_system_timezone():
    """A UTC timestamp that is pre-market in IST must be evaluated in IST,
    not whatever timezone the host machine happens to be in."""
    service = _service()
    # 09:15 IST == 03:45 UTC. Passing 03:44 UTC should be just before open.
    from datetime import timezone as dt_timezone

    just_before_open_utc = datetime(2026, 8, 24, 3, 44, tzinfo=dt_timezone.utc)

    assert service.get_status(just_before_open_utc) == MarketSessionStatus.PRE_MARKET


def test_describe_reports_trading_allowed_flag():
    service = _service()
    open_time = datetime(2026, 8, 24, 12, 0, tzinfo=IST)

    info = service.describe(open_time)

    assert info["is_trading_allowed"] is True
    assert info["status"] == MarketSessionStatus.MARKET_OPEN
    assert info["timezone"] == "Asia/Kolkata"
