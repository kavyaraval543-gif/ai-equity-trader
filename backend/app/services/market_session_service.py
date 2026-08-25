"""Indian equity market session awareness.

All session rules (timezone, hours, holidays) come from configuration —
never hardcoded — so they can be adjusted without touching trading logic.
Always uses Asia/Kolkata (or whatever MARKET_TIMEZONE is set to), never the
host machine's system timezone.
"""
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.models.enums import MarketSessionStatus


class MarketSessionService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._tz = ZoneInfo(self.settings.market_timezone)

    def now(self) -> datetime:
        return datetime.now(self._tz)

    def _session_bounds(self) -> tuple[time, time]:
        start_h, start_m = (int(x) for x in self.settings.market_session_start.split(":"))
        end_h, end_m = (int(x) for x in self.settings.market_session_end.split(":"))
        return time(start_h, start_m), time(end_h, end_m)

    def get_status(self, at: datetime | None = None) -> MarketSessionStatus:
        moment = at.astimezone(self._tz) if at is not None else self.now()

        if moment.weekday() >= 5:  # Saturday=5, Sunday=6
            return MarketSessionStatus.WEEKEND

        if moment.date().isoformat() in self.settings.market_holidays:
            return MarketSessionStatus.HOLIDAY

        session_start, session_end = self._session_bounds()
        current_time = moment.time()

        if current_time < session_start:
            return MarketSessionStatus.PRE_MARKET
        if current_time > session_end:
            return MarketSessionStatus.AFTER_MARKET
        return MarketSessionStatus.MARKET_OPEN

    def is_open(self, at: datetime | None = None) -> bool:
        return self.get_status(at) == MarketSessionStatus.MARKET_OPEN

    def describe(self, at: datetime | None = None) -> dict:
        moment = at.astimezone(self._tz) if at is not None else self.now()
        status = self.get_status(moment)
        return {
            "status": status,
            "current_time": moment,
            "timezone": self.settings.market_timezone,
            "session_start": self.settings.market_session_start,
            "session_end": self.settings.market_session_end,
            "is_trading_allowed": status == MarketSessionStatus.MARKET_OPEN,
        }
