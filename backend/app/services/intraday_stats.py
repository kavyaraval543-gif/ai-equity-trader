"""Daily intraday trading statistics, derived from persisted trades.

Deriving these from the database (rather than in-memory counters) means
they survive a backend restart and stay correct if trades are created by
more than one process — the same reasoning behind the daily risk engine's
live-query approach. Day boundaries are IST calendar days.
"""
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import TradeSide
from app.models.portfolio import Portfolio
from app.models.trade import Trade


@dataclass
class IntradayDailyStats:
    trades_today: int
    realized_pnl_today: float
    consecutive_losses: int
    last_loss_at: datetime | None


def _today_start_ist(settings: Settings) -> datetime:
    now_ist = datetime.now(ZoneInfo(settings.market_timezone))
    return now_ist.replace(hour=0, minute=0, second=0, microsecond=0)


def get_daily_stats(db: Session, portfolio: Portfolio, settings: Settings | None = None) -> IntradayDailyStats:
    settings = settings or get_settings()
    today_start = _today_start_ist(settings)

    trades_today = db.execute(
        select(func.count(Trade.id)).where(Trade.portfolio_id == portfolio.id, Trade.timestamp >= today_start)
    ).scalar_one()

    realized_pnl_today = db.execute(
        select(func.coalesce(func.sum(Trade.realized_pnl), 0.0)).where(
            Trade.portfolio_id == portfolio.id, Trade.timestamp >= today_start
        )
    ).scalar_one()

    # Consecutive losses are counted over closing (SELL) trades, newest
    # first, and stop at the first non-losing trade. Not reset at the day
    # boundary — a losing streak carries across days until a win breaks it.
    closing_trades = db.execute(
        select(Trade)
        .where(Trade.portfolio_id == portfolio.id, Trade.side == TradeSide.SELL)
        .order_by(Trade.timestamp.desc())
        .limit(50)
    ).scalars().all()

    consecutive_losses = 0
    last_loss_at: datetime | None = None
    for trade in closing_trades:
        if (trade.realized_pnl or 0) < 0:
            consecutive_losses += 1
            if last_loss_at is None:
                last_loss_at = trade.timestamp
        else:
            break

    return IntradayDailyStats(
        trades_today=trades_today,
        realized_pnl_today=float(realized_pnl_today),
        consecutive_losses=consecutive_losses,
        last_loss_at=last_loss_at,
    )
