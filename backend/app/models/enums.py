"""Shared enum types persisted across models."""
import enum


class PositionStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class TradeSide(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class SignalType(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class RiskDecisionType(str, enum.Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SystemEventLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class AutonomousTradingState(str, enum.Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class ExitReason(str, enum.Enum):
    STOP_LOSS = "STOP_LOSS"
    TARGET_REACHED = "TARGET_REACHED"
    TRAILING_STOP = "TRAILING_STOP"
    STRATEGY_EXIT = "STRATEGY_EXIT"
    SESSION_END = "SESSION_END"
    MAX_HOLDING_TIME = "MAX_HOLDING_TIME"
    MANUAL = "MANUAL"


class PortfolioKind(str, enum.Enum):
    """Distinguishes the daily SMA(10/30) autonomous trader's portfolio from
    the (separate, isolated) intraday portfolio — they never share cash or
    positions unless explicitly configured to."""

    DAILY = "DAILY"
    INTRADAY = "INTRADAY"


class MarketSessionStatus(str, enum.Enum):
    MARKET_OPEN = "MARKET_OPEN"
    MARKET_CLOSED = "MARKET_CLOSED"
    PRE_MARKET = "PRE_MARKET"
    AFTER_MARKET = "AFTER_MARKET"
    HOLIDAY = "HOLIDAY"
    WEEKEND = "WEEKEND"
