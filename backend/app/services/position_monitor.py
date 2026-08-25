"""Position monitoring — manages EXISTING open positions, independently of
new-entry scanning (the trading orchestrator). Runs on its own interval,
refreshes each open position to the latest real price, and closes a
position when a configured exit rule (stop-loss, target, trailing stop,
max holding time, or session-end) triggers.

Exits still go through the risk engine and the same paper execution
provider as entries — there is no separate, less-guarded exit path.

This single class serves both the daily and intraday traders: it is scoped
to one `portfolio_kind` per instance (never mixes the two), and every
threshold that differs between them (trailing stop, session-end force-close,
max holding time, transaction cost/slippage via the injected execution
provider) is a constructor parameter rather than a hardcoded global —
sharing the algorithm is code reuse, not "running both strategies against
the same portfolio."
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.execution.base import ExecutionProvider
from app.execution.paper import PaperExecutionProvider
from app.market_data.base import MarketDataError, MarketDataProvider
from app.market_data.factory import get_market_data_provider
from app.models.enums import ExitReason, PortfolioKind, PositionStatus, RiskDecisionType, SignalType, SystemEventLevel
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.risk_decision import RiskDecision
from app.models.signal import Signal
from app.risk.engine import RiskEngine
from app.risk.intraday_rules import has_exceeded_max_holding_time
from app.services.event_logger import log_event
from app.services.market_session_service import MarketSessionService
from app.services.portfolio_service import get_or_create_portfolio, recalculate_portfolio
from app.strategies.base import StrategySignal


class PositionMonitor:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        provider: MarketDataProvider | None = None,
        risk_engine: RiskEngine | None = None,
        execution: ExecutionProvider | None = None,
        market_session: MarketSessionService | None = None,
        portfolio_kind: PortfolioKind = PortfolioKind.DAILY,
        trailing_stop_enabled: bool | None = None,
        trailing_stop_percent: float | None = None,
        force_close_at_session_end: bool | None = None,
        max_holding_minutes: int = 0,
        monitor_label: str = "POSITION_MONITOR",
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.provider = provider or get_market_data_provider()
        self.risk_engine = risk_engine or RiskEngine(self.settings)
        self.execution = execution or PaperExecutionProvider(self.settings)
        self.market_session = market_session or MarketSessionService(self.settings)
        self.portfolio_kind = portfolio_kind
        self.trailing_stop_enabled = (
            trailing_stop_enabled if trailing_stop_enabled is not None else self.settings.trailing_stop_enabled
        )
        self.trailing_stop_percent = (
            trailing_stop_percent if trailing_stop_percent is not None else self.settings.trailing_stop_percent
        )
        self.force_close_at_session_end = (
            force_close_at_session_end
            if force_close_at_session_end is not None
            else self.settings.force_close_at_session_end
        )
        self.max_holding_minutes = max_holding_minutes  # 0 disables the check
        self.monitor_label = monitor_label

    def run(self) -> dict:
        portfolio = get_or_create_portfolio(self.db, self.settings, kind=self.portfolio_kind)
        open_positions = self.db.execute(
            select(Position).where(Position.status == PositionStatus.OPEN, Position.portfolio_id == portfolio.id)
        ).scalars().all()

        session_closed = not self.market_session.is_open()
        now = datetime.now(timezone.utc)
        checked = 0
        exits_triggered = 0
        errors = 0

        for position in open_positions:
            checked += 1
            try:
                quote = self.provider.get_latest_price(position.symbol)
            except MarketDataError as exc:
                log_event(
                    self.db, SystemEventLevel.WARNING, "position_monitor",
                    f"Could not fetch a real price for {position.symbol}; leaving position untouched: {exc}",
                )
                errors += 1
                continue

            self.execution.update_position_prices(self.db, {position.symbol: quote.price}, portfolio_id=portfolio.id)

            exit_reason = self._check_exit_rules(position, quote.price, session_closed, now)
            if exit_reason is None:
                continue

            if self._execute_exit(position, portfolio, quote.price, quote.timestamp, exit_reason):
                exits_triggered += 1

        recalculate_portfolio(self.db, portfolio)
        self.db.commit()

        return {
            "checked": checked,
            "exits_triggered": exits_triggered,
            "errors": errors,
            "timestamp": now,
        }

    def _check_exit_rules(
        self, position: Position, price: float, session_closed: bool, now: datetime
    ) -> ExitReason | None:
        if position.stop_loss is not None and price <= position.stop_loss:
            return ExitReason.STOP_LOSS
        if position.target is not None and price >= position.target:
            return ExitReason.TARGET_REACHED
        if self.trailing_stop_enabled:
            trailing_stop_price = position.peak_price * (1 - self.trailing_stop_percent / 100)
            if price <= trailing_stop_price:
                return ExitReason.TRAILING_STOP
        if has_exceeded_max_holding_time(position.opened_at, now, self.max_holding_minutes):
            return ExitReason.MAX_HOLDING_TIME
        if self.force_close_at_session_end and session_closed:
            return ExitReason.SESSION_END
        return None

    def _execute_exit(
        self,
        position: Position,
        portfolio: Portfolio,
        price: float,
        price_timestamp: datetime,
        exit_reason: ExitReason,
    ) -> bool:
        signal = StrategySignal(
            symbol=position.symbol,
            signal_type=SignalType.SELL,
            confidence=1.0,
            strategy_name=self.monitor_label,
            reason=f"Exit rule triggered: {exit_reason.value}.",
            indicator_data={
                "entry_price": position.entry_price,
                "exit_price": price,
                "peak_price": position.peak_price,
                "stop_loss": position.stop_loss,
                "target": position.target,
            },
            market_price=price,
            timestamp=datetime.now(timezone.utc),
        )

        signal_row = Signal(
            symbol=signal.symbol,
            signal_type=signal.signal_type,
            confidence=signal.confidence,
            strategy_name=signal.strategy_name,
            reason=signal.reason,
            indicator_data=signal.indicator_data,
            market_price=signal.market_price,
            timestamp=signal.timestamp,
        )
        self.db.add(signal_row)
        self.db.flush()

        # A price just fetched live for this exit check is never "stale" —
        # staleness applies to cached historical bars, not a fresh quote.
        risk_result = self.risk_engine.evaluate(
            self.db, signal, portfolio, latest_market_timestamp=price_timestamp, is_stale=False,
            exit_reason=exit_reason,
        )
        risk_row = RiskDecision(signal_id=signal_row.id, decision=risk_result.decision, reason=risk_result.reason)
        self.db.add(risk_row)
        self.db.flush()

        log_event(
            self.db,
            SystemEventLevel.INFO if risk_result.decision == RiskDecisionType.APPROVED else SystemEventLevel.WARNING,
            "position_monitor",
            f"{exit_reason.value} decision for {position.symbol}: {risk_result.decision.value} — {risk_result.reason}",
        )

        if risk_result.decision != RiskDecisionType.APPROVED:
            return False

        try:
            self.execution.execute_approved_signal(self.db, risk_result, portfolio)
            self.db.flush()
            log_event(
                self.db, SystemEventLevel.INFO, "position_monitor",
                f"Closed {position.symbol} via {exit_reason.value} at {price:.2f} (paper).",
            )
            return True
        except PermissionError as exc:
            log_event(
                self.db, SystemEventLevel.ERROR, "position_monitor",
                f"Exit execution refused for {position.symbol}: {exc}",
            )
            return False
