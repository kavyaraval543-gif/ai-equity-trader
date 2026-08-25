"""End-to-end proof that an APPROVED BUY signal produces a real paper
position/trade priced at a genuinely fetched real market price.

Live market conditions on any given test run may not naturally produce a
BUY crossover, so this test fetches REAL data from Yahoo Finance (the same
provider the live system uses) and only forces the *signal decision* to
BUY — the price used throughout is the real last close fetched live, never
invented. This tests the risk -> execution wiring, not market data
substitution.
"""
from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.market_data.yahoo_provider import YahooFinanceProvider
from app.models.enums import PositionStatus, RiskDecisionType, SignalType
from app.models.portfolio import Portfolio
from app.risk.engine import RiskEngine
from app.execution.paper import PaperExecutionProvider
from app.strategies.base import StrategySignal


@pytest.mark.network
def test_approved_buy_executes_at_real_fetched_price(db_session):
    provider = YahooFinanceProvider()
    candles = provider.get_historical_data("RELIANCE", interval="1d")
    real_price = candles[-1].close
    assert real_price > 0

    signal = StrategySignal(
        symbol="RELIANCE",
        signal_type=SignalType.BUY,
        confidence=0.9,
        strategy_name="SMA_CROSSOVER",
        reason="forced BUY for end-to-end execution test (price is real, decision is forced)",
        indicator_data={},
        market_price=real_price,
        timestamp=datetime.now(timezone.utc),
    )

    portfolio = Portfolio(
        starting_capital=1_000_000.0, available_cash=1_000_000.0, current_equity=1_000_000.0,
        realized_pnl=0.0, unrealized_pnl=0.0,
    )
    db_session.add(portfolio)
    db_session.flush()

    settings = Settings(_env_file=None)
    risk_engine = RiskEngine(settings)
    risk_decision = risk_engine.evaluate(
        db_session, signal, portfolio, latest_market_timestamp=candles[-1].timestamp, is_stale=False
    )

    assert risk_decision.decision == RiskDecisionType.APPROVED
    assert risk_decision.approved_quantity is not None and risk_decision.approved_quantity > 0

    execution = PaperExecutionProvider(settings)
    trade = execution.execute_approved_signal(db_session, risk_decision, portfolio)

    assert trade.symbol == "RELIANCE"
    assert trade.price == real_price
    assert trade.quantity == risk_decision.approved_quantity

    from sqlalchemy import select
    from app.models.position import Position

    position = db_session.execute(
        select(Position).where(Position.symbol == "RELIANCE", Position.status == PositionStatus.OPEN)
    ).scalar_one()
    assert position.entry_price == real_price
    assert position.quantity == trade.quantity
    assert portfolio.available_cash < 1_000_000.0
