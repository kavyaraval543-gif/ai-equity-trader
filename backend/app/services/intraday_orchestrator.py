"""Runs one intraday trading cycle:

  scan universe on real intraday candles -> validate freshness -> generate
  + store signals -> intraday risk check (which itself runs the full base
  RiskEngine first) -> store risk decisions -> execute approved paper trades
  -> log events

Operates exclusively on the INTRADAY portfolio. It never reads or writes
the daily SMA(10/30) trader's portfolio, positions, or state.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.execution.base import ExecutionProvider
from app.execution.paper import PaperExecutionProvider
from app.models.enums import PortfolioKind, RiskDecisionType, SignalType, SystemEventLevel
from app.models.risk_decision import RiskDecision
from app.models.signal import Signal
from app.risk.intraday_engine import IntradayRiskEngine
from app.schemas.portfolio import PortfolioOut
from app.services.event_logger import log_event
from app.services.intraday_scanner import IntradayScanner
from app.services.intraday_stats import get_daily_stats
from app.services.portfolio_service import get_or_create_portfolio, recalculate_portfolio


class IntradayOrchestrator:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        scanner: IntradayScanner | None = None,
        risk_engine: IntradayRiskEngine | None = None,
        execution: ExecutionProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.scanner = scanner or IntradayScanner(self.settings)
        self.risk_engine = risk_engine or IntradayRiskEngine(self.settings)
        self.execution = execution or PaperExecutionProvider(
            self.settings,
            transaction_cost_percent=self.settings.intraday_transaction_cost_percent,
            stop_loss_percent=self.settings.intraday_stop_loss_percent,
            target_percent=self.settings.intraday_target_percent,
            slippage_percent=self.settings.intraday_slippage_percent,
        )
        self.tz = ZoneInfo(self.settings.market_timezone)

    def run_cycle(self) -> dict:
        started_at = datetime.now(timezone.utc)
        portfolio = get_or_create_portfolio(self.db, self.settings, kind=PortfolioKind.INTRADAY)
        stats = get_daily_stats(self.db, portfolio, self.settings)
        now_ist = datetime.now(self.tz)

        signals_generated = 0
        trades_executed = 0
        errors = 0
        symbol_results: list[dict] = []

        for scan in self.scanner.scan_all():
            if scan.error is not None or scan.signal is None:
                log_event(
                    self.db, SystemEventLevel.WARNING, "intraday_cycle",
                    f"Skipping {scan.symbol}: {scan.error or 'no signal produced'}.",
                )
                errors += 1
                symbol_results.append({"symbol": scan.symbol, "status": "market_data_error", "error": scan.error})
                continue

            signal = scan.signal
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
            signals_generated += 1

            if signal.signal_type == SignalType.HOLD:
                symbol_results.append({"symbol": scan.symbol, "status": "ok", "signal": signal.signal_type.value})
                continue

            risk_result = self.risk_engine.evaluate_intraday(
                self.db,
                signal,
                portfolio,
                latest_market_timestamp=scan.latest_bar_time,
                is_stale=scan.is_stale,
                current_time_ist=now_ist,
                consecutive_losses=stats.consecutive_losses,
                last_loss_at=stats.last_loss_at,
            )
            risk_row = RiskDecision(
                signal_id=signal_row.id, decision=risk_result.decision, reason=risk_result.reason
            )
            self.db.add(risk_row)
            self.db.flush()

            log_event(
                self.db,
                SystemEventLevel.INFO if risk_result.decision == RiskDecisionType.APPROVED else SystemEventLevel.WARNING,
                "intraday_risk",
                f"Intraday risk decision for {scan.symbol}: {risk_result.decision.value} — {risk_result.reason}",
            )

            if risk_result.decision != RiskDecisionType.APPROVED:
                symbol_results.append(
                    {"symbol": scan.symbol, "status": "ok", "signal": signal.signal_type.value, "risk": "REJECTED"}
                )
                continue

            try:
                trade = self.execution.execute_approved_signal(self.db, risk_result, portfolio)
                self.db.flush()
                trades_executed += 1
                log_event(
                    self.db, SystemEventLevel.INFO, "intraday_execution",
                    f"Executed intraday {trade.side.value} {trade.quantity} {scan.symbol} @ {trade.price:.2f} (paper).",
                )
                symbol_results.append(
                    {"symbol": scan.symbol, "status": "ok", "signal": signal.signal_type.value, "risk": "APPROVED",
                     "trade_id": trade.id}
                )
                # Refresh stats so later symbols in this same cycle see the
                # updated trade count / P&L rather than a stale snapshot.
                stats = get_daily_stats(self.db, portfolio, self.settings)
            except PermissionError as exc:
                errors += 1
                log_event(
                    self.db, SystemEventLevel.ERROR, "intraday_execution",
                    f"Intraday execution refused for {scan.symbol}: {exc}",
                )
                symbol_results.append({"symbol": scan.symbol, "status": "execution_error", "error": str(exc)})

        recalculate_portfolio(self.db, portfolio)
        self.db.commit()
        self.db.refresh(portfolio)

        return {
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc),
            "symbols": symbol_results,
            "signals_generated": signals_generated,
            "trades_executed": trades_executed,
            "errors": errors,
            "portfolio": PortfolioOut.model_validate(portfolio),
        }
