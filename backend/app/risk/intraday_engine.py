"""Intraday risk engine — extends (never bypasses) the shared `RiskEngine`.

`evaluate_intraday` always runs the full base `RiskEngine.evaluate` first
(emergency stop, stale/invalid data, duplicate position, max simultaneous
positions, max trades/day, max daily loss, insufficient cash, position
sizing — all still enforced, just reconfigured with intraday thresholds via
a copy of settings). Only if the base engine approves does it layer on the
intraday-only checks: max consecutive losses, cooldown after a loss, and no
new entries near session close. Exits are never subject to the extra checks
— consistent with the base engine's own "protective exits always fire"
design.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.enums import ExitReason, RiskDecisionType, SignalType
from app.models.portfolio import Portfolio
from app.risk import intraday_rules
from app.risk.engine import RiskEngine
from app.risk.schemas import RiskDecisionResult
from app.strategies.base import StrategySignal


class IntradayRiskEngine(RiskEngine):
    def __init__(self, settings: Settings | None = None) -> None:
        base_settings = settings or get_settings()
        intraday_settings = base_settings.model_copy(
            update={
                "risk_max_position_pct": base_settings.intraday_risk_max_capital_per_trade_pct,
                "risk_max_simultaneous_positions": base_settings.intraday_risk_max_simultaneous_positions,
                "risk_max_trades_per_day": base_settings.intraday_risk_max_trades_per_day,
                "risk_max_daily_loss_pct": base_settings.intraday_risk_max_daily_loss_pct,
                "risk_transaction_cost_bps": base_settings.intraday_transaction_cost_percent * 100,
            }
        )
        super().__init__(intraday_settings)
        self._intraday_settings = base_settings

    def evaluate_intraday(
        self,
        db: Session,
        signal: StrategySignal,
        portfolio: Portfolio,
        latest_market_timestamp: datetime,
        is_stale: bool,
        current_time_ist: datetime,
        consecutive_losses: int,
        last_loss_at: datetime | None,
        exit_reason: ExitReason | None = None,
    ) -> RiskDecisionResult:
        base_result = self.evaluate(db, signal, portfolio, latest_market_timestamp, is_stale, exit_reason)
        if base_result.decision != RiskDecisionType.APPROVED or signal.signal_type != SignalType.BUY:
            return base_result

        s = self._intraday_settings

        if intraday_rules.is_max_consecutive_losses_reached(consecutive_losses, s.intraday_risk_max_consecutive_losses):
            return RiskDecisionResult(
                signal=signal,
                decision=RiskDecisionType.REJECTED,
                reason=(
                    f"Maximum consecutive losses reached "
                    f"({consecutive_losses}/{s.intraday_risk_max_consecutive_losses}) — no new entries."
                ),
                exit_reason=exit_reason,
            )

        if intraday_rules.is_in_cooldown(current_time_ist, last_loss_at, s.intraday_risk_cooldown_minutes):
            return RiskDecisionResult(
                signal=signal,
                decision=RiskDecisionType.REJECTED,
                reason=f"In cooldown after a losing trade ({s.intraday_risk_cooldown_minutes} minutes).",
                exit_reason=exit_reason,
            )

        if intraday_rules.is_near_session_end(current_time_ist, s.market_session_end, s.intraday_no_entry_minutes_before_close):
            return RiskDecisionResult(
                signal=signal,
                decision=RiskDecisionType.REJECTED,
                reason=(
                    f"Too close to session end ({s.intraday_no_entry_minutes_before_close} minute cutoff) "
                    "— no new entries."
                ),
                exit_reason=exit_reason,
            )

        return base_result
