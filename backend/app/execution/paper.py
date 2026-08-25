"""Simulated (paper) order execution. No broker credentials, no real orders,
no live execution — every trade here is a bookkeeping entry against a
virtual cash balance, priced using real fetched market prices.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.execution.base import ExecutionProvider
from app.models.enums import ExitReason, PositionStatus, RiskDecisionType, SignalType, TradeSide
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.trade import Trade
from app.risk.schemas import RiskDecisionResult


class PaperExecutionProvider(ExecutionProvider):
    name = "paper"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def execute_approved_signal(
        self,
        db: Session,
        risk_decision: RiskDecisionResult,
        portfolio: Portfolio,
    ) -> Trade:
        if risk_decision.decision != RiskDecisionType.APPROVED:
            raise PermissionError(
                f"Refusing to execute: risk decision is {risk_decision.decision}, not APPROVED."
            )
        if not risk_decision.approved_quantity or risk_decision.approved_quantity < 1:
            raise PermissionError("Refusing to execute: risk decision carries no approved quantity.")

        signal = risk_decision.signal
        if signal.signal_type == SignalType.BUY:
            return self._execute_buy(db, risk_decision, portfolio)
        if signal.signal_type == SignalType.SELL:
            return self._execute_sell(db, risk_decision, portfolio)
        raise PermissionError(f"Refusing to execute: signal type {signal.signal_type} is not tradable.")

    def _execute_buy(self, db: Session, risk_decision: RiskDecisionResult, portfolio: Portfolio) -> Trade:
        signal = risk_decision.signal
        quantity = risk_decision.approved_quantity
        price = signal.market_price
        transaction_cost = quantity * price * (self.settings.risk_transaction_cost_bps / 10_000)
        total_cost = quantity * price + transaction_cost

        if total_cost > portfolio.available_cash:
            # Belt-and-braces: the risk engine already sized this to fit, but
            # execution must never spend cash it doesn't have.
            raise PermissionError(
                f"Refusing to execute BUY: total cost {total_cost:.2f} exceeds available cash "
                f"{portfolio.available_cash:.2f}."
            )

        stop_loss = (
            price * (1 - self.settings.stop_loss_percent / 100) if self.settings.stop_loss_percent else None
        )
        target = price * (1 + self.settings.target_percent / 100) if self.settings.target_percent else None

        position = Position(
            portfolio_id=portfolio.id,
            symbol=signal.symbol,
            quantity=quantity,
            entry_price=price,
            current_price=price,
            stop_loss=stop_loss,
            target=target,
            peak_price=price,
            unrealized_pnl=0.0,
            status=PositionStatus.OPEN,
        )
        db.add(position)
        db.flush()

        trade = Trade(
            portfolio_id=portfolio.id,
            position_id=position.id,
            symbol=signal.symbol,
            side=TradeSide.BUY,
            quantity=quantity,
            price=price,
            transaction_cost=transaction_cost,
            realized_pnl=None,
            strategy_name=signal.strategy_name,
        )
        db.add(trade)

        portfolio.available_cash -= total_cost
        db.add(portfolio)
        db.flush()
        return trade

    def _execute_sell(self, db: Session, risk_decision: RiskDecisionResult, portfolio: Portfolio) -> Trade:
        signal = risk_decision.signal
        position = db.execute(
            select(Position).where(Position.symbol == signal.symbol, Position.status == PositionStatus.OPEN)
        ).scalar_one_or_none()
        if position is None:
            raise PermissionError(f"Refusing to execute SELL: no open position for {signal.symbol}.")

        quantity = position.quantity
        price = signal.market_price
        transaction_cost = quantity * price * (self.settings.risk_transaction_cost_bps / 10_000)
        proceeds = quantity * price - transaction_cost
        # Net of the exit-side transaction cost against price movement since entry.
        # The entry-side cost was already realized as a cash outflow at BUY time.
        realized_pnl = (price - position.entry_price) * quantity - transaction_cost

        position.status = PositionStatus.CLOSED
        position.closed_at = datetime.now(timezone.utc)
        position.current_price = price
        position.unrealized_pnl = 0.0
        db.add(position)

        trade = Trade(
            portfolio_id=portfolio.id,
            position_id=position.id,
            symbol=signal.symbol,
            side=TradeSide.SELL,
            quantity=quantity,
            price=price,
            transaction_cost=transaction_cost,
            realized_pnl=realized_pnl,
            strategy_name=signal.strategy_name,
            exit_reason=risk_decision.exit_reason or ExitReason.STRATEGY_EXIT,
        )
        db.add(trade)

        portfolio.available_cash += proceeds
        portfolio.realized_pnl += realized_pnl
        db.add(portfolio)
        db.flush()
        return trade

    def update_position_prices(self, db: Session, price_lookup: dict[str, float]) -> None:
        open_positions = db.execute(select(Position).where(Position.status == PositionStatus.OPEN)).scalars().all()
        for position in open_positions:
            price = price_lookup.get(position.symbol)
            if price is None:
                continue
            position.current_price = price
            position.unrealized_pnl = (price - position.entry_price) * position.quantity
            position.peak_price = max(position.peak_price, price)
            db.add(position)
