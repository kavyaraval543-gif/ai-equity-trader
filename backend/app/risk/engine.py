"""The risk engine. Every BUY/SELL signal must pass through `RiskEngine.evaluate`
before any trade may be executed. It only ever returns APPROVED or REJECTED,
always with a reason. Any internal error is treated as REJECTED — it never
fails open.

Design note: controls that would let the portfolio take on MORE risk
(emergency stop, max trades/day, max daily loss, max simultaneous positions,
duplicate-position, insufficient cash) apply only to BUY signals. Controls
that protect against acting on bad data (stale data, invalid price) and the
"must have a position to close" check apply to both BUY and SELL. This means
a stop-loss/target exit can still fire during an emergency stop or after the
daily loss limit is hit — blocking a protective exit in exactly the moment
risk limits are breached would be the wrong failure mode.
"""
import math
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import ExitReason, PositionStatus, RiskDecisionType, SignalType
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.trade import Trade
from app.risk.schemas import RiskDecisionResult
from app.strategies.base import StrategySignal


class RiskEngine:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def evaluate(
        self,
        db: Session,
        signal: StrategySignal,
        portfolio: Portfolio,
        latest_market_timestamp: datetime,
        is_stale: bool,
        exit_reason: ExitReason | None = None,
    ) -> RiskDecisionResult:
        try:
            return self._evaluate(db, signal, portfolio, latest_market_timestamp, is_stale, exit_reason)
        except Exception as exc:  # noqa: BLE001 — any risk-calculation failure must reject, never approve
            return RiskDecisionResult(
                signal=signal,
                decision=RiskDecisionType.REJECTED,
                reason=f"Risk evaluation error — rejecting for safety: {exc}",
                exit_reason=exit_reason,
            )

    def _today_start_ist(self) -> datetime:
        """IST calendar-day boundary for daily limits (not UTC midnight)."""
        now_ist = datetime.now(ZoneInfo(self.settings.market_timezone))
        return now_ist.replace(hour=0, minute=0, second=0, microsecond=0)

    def _evaluate(
        self,
        db: Session,
        signal: StrategySignal,
        portfolio: Portfolio,
        latest_market_timestamp: datetime,
        is_stale: bool,
        exit_reason: ExitReason | None,
    ) -> RiskDecisionResult:
        def rejected(reason: str) -> RiskDecisionResult:
            return RiskDecisionResult(
                signal=signal, decision=RiskDecisionType.REJECTED, reason=reason, exit_reason=exit_reason
            )

        def approved(reason: str, quantity: int) -> RiskDecisionResult:
            return RiskDecisionResult(
                signal=signal,
                decision=RiskDecisionType.APPROVED,
                reason=reason,
                approved_quantity=quantity,
                exit_reason=exit_reason,
            )

        if signal.signal_type == SignalType.HOLD:
            return rejected("HOLD signals are not actionable and cannot be executed.")

        # Data-quality checks apply to both entries and exits — never act on
        # a price we can't trust, in either direction.
        if is_stale:
            return rejected(
                f"Stale market data for {signal.symbol}: latest bar is from {latest_market_timestamp.isoformat()}."
            )
        if signal.market_price is None or signal.market_price <= 0:
            return rejected(f"Invalid market price for {signal.symbol}: {signal.market_price}.")

        open_position = db.execute(
            select(Position).where(Position.symbol == signal.symbol, Position.status == PositionStatus.OPEN)
        ).scalar_one_or_none()

        if signal.signal_type == SignalType.SELL:
            if open_position is None:
                return rejected(f"No open position to sell for {signal.symbol}.")
            return approved(
                f"Approved SELL closing the open {open_position.quantity}-share position in {signal.symbol}.",
                open_position.quantity,
            )

        # --- Everything below applies to BUY (new-entry) signals only. ---

        if self.settings.emergency_stop:
            return rejected("Emergency stop is active — no new entries are permitted.")

        if open_position is not None:
            return rejected(f"Duplicate position: already holding an open position in {signal.symbol}.")

        today_start = self._today_start_ist()
        trades_today = db.execute(
            select(func.count(Trade.id)).where(Trade.portfolio_id == portfolio.id, Trade.timestamp >= today_start)
        ).scalar_one()
        if trades_today >= self.settings.risk_max_trades_per_day:
            return rejected(
                f"Maximum trades per day reached ({trades_today}/{self.settings.risk_max_trades_per_day})."
            )

        realized_pnl_today = db.execute(
            select(func.coalesce(func.sum(Trade.realized_pnl), 0.0)).where(
                Trade.portfolio_id == portfolio.id, Trade.timestamp >= today_start
            )
        ).scalar_one()
        max_daily_loss = self.settings.risk_max_daily_loss_pct * portfolio.starting_capital
        if realized_pnl_today <= -max_daily_loss:
            return rejected(
                f"Maximum daily loss limit reached (realized {realized_pnl_today:.2f} vs "
                f"limit -{max_daily_loss:.2f})."
            )

        open_position_count = db.execute(
            select(func.count(Position.id)).where(Position.status == PositionStatus.OPEN)
        ).scalar_one()
        if open_position_count >= self.settings.risk_max_simultaneous_positions:
            return rejected(
                f"Maximum simultaneous positions reached "
                f"({open_position_count}/{self.settings.risk_max_simultaneous_positions})."
            )

        cost_multiplier = 1 + (self.settings.risk_transaction_cost_bps / 10_000)
        max_affordable_qty = math.floor(portfolio.available_cash / (signal.market_price * cost_multiplier))
        position_cap_value = self.settings.risk_max_position_pct * portfolio.current_equity
        position_cap_qty = math.floor(position_cap_value / signal.market_price)
        quantity = min(max_affordable_qty, position_cap_qty)

        if quantity < 1:
            return rejected(
                f"Insufficient cash or position size too small for {signal.symbol} at "
                f"{signal.market_price:.2f} (available cash {portfolio.available_cash:.2f}, "
                f"max position value {position_cap_value:.2f})."
            )

        return approved(
            f"Approved BUY of {quantity} shares of {signal.symbol} at {signal.market_price:.2f} "
            f"(within {self.settings.risk_max_position_pct:.0%} position cap and available cash).",
            quantity,
        )
