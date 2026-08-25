"""Runs one complete trading cycle:

  fetch real market data -> validate -> run strategies -> generate + store
  signals -> risk-check -> store risk decisions -> execute approved trades
  -> mark positions to market -> recalculate portfolio -> log events

No step here may substitute synthetic data, and no trade may execute
without a stored APPROVED RiskDecision.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.execution.base import ExecutionProvider
from app.execution.paper import PaperExecutionProvider
from app.market_data.base import MarketDataError, MarketDataProvider
from app.market_data.factory import get_market_data_provider
from app.models.enums import RiskDecisionType, SignalType, SystemEventLevel
from app.models.risk_decision import RiskDecision
from app.models.signal import Signal
from app.risk.engine import RiskEngine
from app.schemas.portfolio import PortfolioOut
from app.schemas.risk import RiskDecisionOut
from app.schemas.signal import SignalOut
from app.schemas.trade import TradeOut
from app.schemas.trading import RunCycleResult, SymbolCycleResult
from app.services.event_logger import log_event
from app.services.market_data_service import MarketDataService
from app.services.portfolio_service import get_or_create_portfolio, recalculate_portfolio
from app.strategies.base import BaseStrategy
from app.strategies.sma_crossover import SmaCrossoverStrategy


class TradingOrchestrator:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        provider: MarketDataProvider | None = None,
        strategies: list[BaseStrategy] | None = None,
        risk_engine: RiskEngine | None = None,
        execution: ExecutionProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = settings or get_settings()
        self.provider = provider or get_market_data_provider()
        self.market_data_service = MarketDataService(self.provider, db, self.settings)
        self.strategies = strategies or [SmaCrossoverStrategy()]
        self.risk_engine = risk_engine or RiskEngine(self.settings)
        self.execution = execution or PaperExecutionProvider(self.settings)

    def run_cycle(self) -> RunCycleResult:
        started_at = datetime.now(timezone.utc)
        portfolio = get_or_create_portfolio(self.db, self.settings)

        symbol_results: list[SymbolCycleResult] = []
        price_lookup: dict[str, float] = {}
        signals_generated = 0
        trades_executed = 0
        error_count = 0

        for symbol in self.settings.market_data_symbols:
            try:
                result = self._process_symbol(symbol, portfolio, price_lookup)
                symbol_results.append(result)
                if result.signal is not None:
                    signals_generated += 1
                if result.trade is not None:
                    trades_executed += 1
                if result.status != "ok":
                    error_count += 1
            except Exception as exc:  # noqa: BLE001 — one symbol's failure must not abort the cycle
                log_event(
                    self.db,
                    SystemEventLevel.ERROR,
                    "trading_cycle",
                    f"Unexpected error processing {symbol}: {exc}",
                )
                symbol_results.append(SymbolCycleResult(symbol=symbol, status="unexpected_error", error=str(exc)))
                error_count += 1

        self.execution.update_position_prices(self.db, price_lookup, portfolio_id=portfolio.id)
        recalculate_portfolio(self.db, portfolio)
        self.db.commit()
        self.db.refresh(portfolio)

        completed_at = datetime.now(timezone.utc)
        return RunCycleResult(
            started_at=started_at,
            completed_at=completed_at,
            symbols=symbol_results,
            signals_generated=signals_generated,
            trades_executed=trades_executed,
            errors=error_count,
            portfolio=PortfolioOut.model_validate(portfolio),
        )

    def _process_symbol(
        self, symbol: str, portfolio, price_lookup: dict[str, float]
    ) -> SymbolCycleResult:
        # Step 1 + 2: fetch real data and validate it.
        try:
            candles = self.market_data_service.get_historical_data(symbol, self.settings.market_data_timeframe)
        except MarketDataError as exc:
            log_event(
                self.db, SystemEventLevel.ERROR, "market_data", f"Market data fetch failed for {symbol}: {exc}"
            )
            return SymbolCycleResult(symbol=symbol, status="market_data_error", error=str(exc))

        latest_candle = candles[-1]
        if latest_candle.close <= 0:
            log_event(
                self.db, SystemEventLevel.ERROR, "market_data", f"Invalid price for {symbol}: {latest_candle.close}"
            )
            return SymbolCycleResult(symbol=symbol, status="invalid_price", error="Non-positive price")

        price_lookup[symbol] = latest_candle.close
        is_stale = self.market_data_service.is_stale(latest_candle.timestamp)
        if is_stale:
            log_event(
                self.db,
                SystemEventLevel.WARNING,
                "market_data",
                f"Stale market data for {symbol}: latest bar is from {latest_candle.timestamp.isoformat()}.",
            )

        # Step 3 + 4: run strategies, generate and store a signal.
        # (Phase 2 runs a single strategy; the loop keeps this extensible.)
        strategy_signal = self.strategies[0].generate_signal(symbol, candles)

        signal_row = Signal(
            symbol=strategy_signal.symbol,
            signal_type=strategy_signal.signal_type,
            confidence=strategy_signal.confidence,
            strategy_name=strategy_signal.strategy_name,
            reason=strategy_signal.reason,
            indicator_data=strategy_signal.indicator_data,
            market_price=strategy_signal.market_price,
            timestamp=strategy_signal.timestamp,
        )
        self.db.add(signal_row)
        self.db.flush()
        log_event(
            self.db,
            SystemEventLevel.INFO,
            "signal",
            f"{strategy_signal.strategy_name} generated {strategy_signal.signal_type.value} for {symbol}.",
            details={"confidence": strategy_signal.confidence, "reason": strategy_signal.reason},
        )

        if strategy_signal.signal_type == SignalType.HOLD:
            return SymbolCycleResult(symbol=symbol, status="ok", signal=SignalOut.model_validate(signal_row))

        # Step 5 + 6: risk-check the actionable signal and store the decision.
        risk_result = self.risk_engine.evaluate(
            self.db, strategy_signal, portfolio, latest_candle.timestamp, is_stale
        )
        risk_row = RiskDecision(signal_id=signal_row.id, decision=risk_result.decision, reason=risk_result.reason)
        self.db.add(risk_row)
        self.db.flush()
        log_event(
            self.db,
            SystemEventLevel.INFO if risk_result.decision == RiskDecisionType.APPROVED else SystemEventLevel.WARNING,
            "risk",
            f"Risk decision for {symbol}: {risk_result.decision.value} — {risk_result.reason}",
        )

        if risk_result.decision != RiskDecisionType.APPROVED:
            return SymbolCycleResult(
                symbol=symbol,
                status="ok",
                signal=SignalOut.model_validate(signal_row),
                risk_decision=RiskDecisionOut.model_validate(risk_row),
            )

        # Step 7: execute — only reachable with a stored APPROVED RiskDecision.
        try:
            trade = self.execution.execute_approved_signal(self.db, risk_result, portfolio)
            self.db.flush()
            log_event(
                self.db,
                SystemEventLevel.INFO,
                "execution",
                f"Executed {trade.side.value} {trade.quantity} {symbol} @ {trade.price:.2f} (paper).",
            )
            return SymbolCycleResult(
                symbol=symbol,
                status="ok",
                signal=SignalOut.model_validate(signal_row),
                risk_decision=RiskDecisionOut.model_validate(risk_row),
                trade=TradeOut.model_validate(trade),
            )
        except PermissionError as exc:
            log_event(self.db, SystemEventLevel.ERROR, "execution", f"Execution refused for {symbol}: {exc}")
            return SymbolCycleResult(
                symbol=symbol,
                status="execution_error",
                signal=SignalOut.model_validate(signal_row),
                risk_decision=RiskDecisionOut.model_validate(risk_row),
                error=str(exc),
            )
