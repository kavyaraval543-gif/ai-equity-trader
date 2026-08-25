"""Verifies the paper execution provider, and — critically — that it is
architecturally impossible to execute a trade without a stored APPROVED
RiskDecision."""
from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.execution.paper import PaperExecutionProvider
from app.models.enums import PositionStatus, RiskDecisionType, SignalType
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.risk.schemas import RiskDecisionResult
from app.strategies.base import StrategySignal

NOW = datetime.now(timezone.utc)


def _settings() -> Settings:
    return Settings(_env_file=None, risk_transaction_cost_bps=10.0)


def _portfolio(db) -> Portfolio:
    p = Portfolio(starting_capital=1_000_000.0, available_cash=1_000_000.0, current_equity=1_000_000.0,
                  realized_pnl=0.0, unrealized_pnl=0.0)
    db.add(p)
    db.flush()
    return p


def _buy_signal(price=1000.0) -> StrategySignal:
    return StrategySignal(
        symbol="RELIANCE", signal_type=SignalType.BUY, confidence=0.8, strategy_name="SMA_CROSSOVER",
        reason="test", indicator_data={}, market_price=price, timestamp=NOW,
    )


def test_rejects_execution_without_approved_decision(db_session):
    """The hard architectural requirement: REJECTED decisions must never execute."""
    portfolio = _portfolio(db_session)
    provider = PaperExecutionProvider(_settings())
    rejected = RiskDecisionResult(signal=_buy_signal(), decision=RiskDecisionType.REJECTED, reason="test rejection")

    with pytest.raises(PermissionError):
        provider.execute_approved_signal(db_session, rejected, portfolio)


def test_rejects_approved_decision_without_quantity(db_session):
    portfolio = _portfolio(db_session)
    provider = PaperExecutionProvider(_settings())
    approved_no_qty = RiskDecisionResult(
        signal=_buy_signal(), decision=RiskDecisionType.APPROVED, reason="test", approved_quantity=None
    )

    with pytest.raises(PermissionError):
        provider.execute_approved_signal(db_session, approved_no_qty, portfolio)


def test_buy_execution_creates_position_and_updates_cash(db_session):
    portfolio = _portfolio(db_session)
    provider = PaperExecutionProvider(_settings())
    approved = RiskDecisionResult(
        signal=_buy_signal(price=1000.0), decision=RiskDecisionType.APPROVED, reason="test", approved_quantity=100
    )

    trade = provider.execute_approved_signal(db_session, approved, portfolio)

    expected_cost = 100 * 1000.0 * 1.001  # 10 bps transaction cost
    assert trade.quantity == 100
    assert trade.price == 1000.0
    assert portfolio.available_cash == pytest.approx(1_000_000.0 - expected_cost)

    position = db_session.query(Position).filter_by(symbol="RELIANCE", status=PositionStatus.OPEN).one()
    assert position.quantity == 100
    assert position.entry_price == 1000.0


def test_sell_execution_closes_position_and_realizes_pnl(db_session):
    portfolio = _portfolio(db_session)
    position = Position(
        portfolio_id=portfolio.id, symbol="RELIANCE", quantity=100, entry_price=1000.0, current_price=1000.0,
        peak_price=1000.0, status=PositionStatus.OPEN,
    )
    db_session.add(position)
    db_session.flush()
    portfolio.available_cash -= 100 * 1000.0  # simulate the cash already spent on entry

    provider = PaperExecutionProvider(_settings())
    sell_signal = StrategySignal(
        symbol="RELIANCE", signal_type=SignalType.SELL, confidence=0.8, strategy_name="SMA_CROSSOVER",
        reason="test", indicator_data={}, market_price=1100.0, timestamp=NOW,
    )
    approved = RiskDecisionResult(
        signal=sell_signal, decision=RiskDecisionType.APPROVED, reason="test", approved_quantity=100
    )

    trade = provider.execute_approved_signal(db_session, approved, portfolio)

    assert position.status == PositionStatus.CLOSED
    assert position.closed_at is not None
    assert trade.realized_pnl == pytest.approx((1100.0 - 1000.0) * 100 - (100 * 1100.0 * 0.001))
    assert portfolio.realized_pnl == pytest.approx(trade.realized_pnl)


def test_update_position_prices_marks_to_market(db_session):
    portfolio = _portfolio(db_session)
    position = Position(
        portfolio_id=portfolio.id, symbol="RELIANCE", quantity=50, entry_price=1000.0, current_price=1000.0,
        peak_price=1000.0, status=PositionStatus.OPEN,
    )
    db_session.add(position)
    db_session.flush()

    provider = PaperExecutionProvider(_settings())
    provider.update_position_prices(db_session, {"RELIANCE": 1050.0})

    assert position.current_price == 1050.0
    assert position.unrealized_pnl == pytest.approx((1050.0 - 1000.0) * 50)
