from datetime import datetime, timedelta, timezone

from app.core.config import Settings
from app.models.enums import PositionStatus, RiskDecisionType, SignalType, TradeSide
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.trade import Trade
from app.risk.engine import RiskEngine
from app.strategies.base import StrategySignal

NOW = datetime.now(timezone.utc)


def _settings(**overrides) -> Settings:
    defaults = dict(
        emergency_stop=False,
        risk_max_position_pct=0.10,
        risk_max_simultaneous_positions=5,
        risk_max_trades_per_day=10,
        risk_max_daily_loss_pct=0.03,
        risk_transaction_cost_bps=5.0,
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _portfolio(db, **overrides) -> Portfolio:
    defaults = dict(starting_capital=1_000_000.0, available_cash=1_000_000.0, current_equity=1_000_000.0,
                     realized_pnl=0.0, unrealized_pnl=0.0)
    defaults.update(overrides)
    p = Portfolio(**defaults)
    db.add(p)
    db.flush()
    return p


def _buy_signal(symbol="RELIANCE", price=1300.0) -> StrategySignal:
    return StrategySignal(
        symbol=symbol,
        signal_type=SignalType.BUY,
        confidence=0.8,
        strategy_name="SMA_CROSSOVER",
        reason="test",
        indicator_data={},
        market_price=price,
        timestamp=NOW,
    )


def _sell_signal(symbol="RELIANCE", price=1300.0) -> StrategySignal:
    return StrategySignal(
        symbol=symbol,
        signal_type=SignalType.SELL,
        confidence=0.8,
        strategy_name="SMA_CROSSOVER",
        reason="test",
        indicator_data={},
        market_price=price,
        timestamp=NOW,
    )


def test_buy_approved_and_sized_within_position_cap(db_session):
    portfolio = _portfolio(db_session)
    engine = RiskEngine(_settings())

    result = engine.evaluate(db_session, _buy_signal(price=1000.0), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.APPROVED
    # 10% of 1,000,000 equity / price 1000 = 100 shares cap.
    assert result.approved_quantity == 100


def test_emergency_stop_rejects(db_session):
    portfolio = _portfolio(db_session)
    engine = RiskEngine(_settings(emergency_stop=True))

    result = engine.evaluate(db_session, _buy_signal(), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "Emergency stop" in result.reason


def test_hold_signal_rejected_as_not_actionable(db_session):
    portfolio = _portfolio(db_session)
    engine = RiskEngine(_settings())
    hold_signal = StrategySignal(
        symbol="RELIANCE", signal_type=SignalType.HOLD, confidence=0.5, strategy_name="SMA_CROSSOVER",
        reason="test", indicator_data={}, market_price=1000.0, timestamp=NOW,
    )

    result = engine.evaluate(db_session, hold_signal, portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "not actionable" in result.reason


def test_stale_data_rejects(db_session):
    portfolio = _portfolio(db_session)
    engine = RiskEngine(_settings())

    result = engine.evaluate(db_session, _buy_signal(), portfolio, NOW - timedelta(days=5), is_stale=True)

    assert result.decision == RiskDecisionType.REJECTED
    assert "Stale market data" in result.reason


def test_invalid_price_rejects(db_session):
    portfolio = _portfolio(db_session)
    engine = RiskEngine(_settings())

    result = engine.evaluate(db_session, _buy_signal(price=0.0), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "Invalid market price" in result.reason


def test_duplicate_position_rejects_buy(db_session):
    portfolio = _portfolio(db_session)
    db_session.add(
        Position(
            portfolio_id=portfolio.id, symbol="RELIANCE", quantity=10, entry_price=1000.0, current_price=1000.0,
            peak_price=1000.0, status=PositionStatus.OPEN,
        )
    )
    db_session.flush()
    engine = RiskEngine(_settings())

    result = engine.evaluate(db_session, _buy_signal(), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "Duplicate position" in result.reason


def test_sell_without_open_position_rejects(db_session):
    portfolio = _portfolio(db_session)
    engine = RiskEngine(_settings())

    result = engine.evaluate(db_session, _sell_signal(), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "No open position to sell" in result.reason


def test_sell_with_open_position_approved(db_session):
    portfolio = _portfolio(db_session)
    db_session.add(
        Position(
            portfolio_id=portfolio.id, symbol="RELIANCE", quantity=10, entry_price=1000.0, current_price=1000.0,
            peak_price=1000.0, status=PositionStatus.OPEN,
        )
    )
    db_session.flush()
    engine = RiskEngine(_settings())

    result = engine.evaluate(db_session, _sell_signal(), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.APPROVED
    assert result.approved_quantity == 10


def test_max_simultaneous_positions_rejects(db_session):
    portfolio = _portfolio(db_session)
    for i, symbol in enumerate(["A", "B"]):
        db_session.add(
            Position(
                portfolio_id=portfolio.id, symbol=symbol, quantity=1, entry_price=100.0, current_price=100.0,
                peak_price=100.0, status=PositionStatus.OPEN,
            )
        )
    db_session.flush()
    engine = RiskEngine(_settings(risk_max_simultaneous_positions=2))

    result = engine.evaluate(db_session, _buy_signal(symbol="RELIANCE"), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "Maximum simultaneous positions" in result.reason


def test_max_trades_per_day_rejects(db_session):
    portfolio = _portfolio(db_session)
    for _ in range(2):
        db_session.add(
            Trade(
                portfolio_id=portfolio.id, symbol="X", side=TradeSide.BUY, quantity=1, price=100.0,
                transaction_cost=0.0, strategy_name="SMA_CROSSOVER", timestamp=NOW,
            )
        )
    db_session.flush()
    engine = RiskEngine(_settings(risk_max_trades_per_day=2))

    result = engine.evaluate(db_session, _buy_signal(), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "Maximum trades per day" in result.reason


def test_max_daily_loss_rejects(db_session):
    portfolio = _portfolio(db_session, starting_capital=1_000_000.0)
    db_session.add(
        Trade(
            portfolio_id=portfolio.id, symbol="X", side=TradeSide.SELL, quantity=1, price=100.0,
            transaction_cost=0.0, realized_pnl=-40_000.0, strategy_name="SMA_CROSSOVER", timestamp=NOW,
        )
    )
    db_session.flush()
    engine = RiskEngine(_settings(risk_max_daily_loss_pct=0.03))  # limit = 30,000

    result = engine.evaluate(db_session, _buy_signal(), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "Maximum daily loss" in result.reason


def test_insufficient_cash_rejects(db_session):
    portfolio = _portfolio(db_session, available_cash=50.0, current_equity=50.0, starting_capital=50.0)
    engine = RiskEngine(_settings())

    result = engine.evaluate(db_session, _buy_signal(price=1000.0), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "Insufficient cash" in result.reason


def test_risk_engine_never_raises_and_rejects_on_internal_error(db_session):
    """Simulates a risk-calculation failure via a broken portfolio value —
    the engine must reject, never approve or propagate the exception."""
    portfolio = _portfolio(db_session)
    portfolio.starting_capital = None  # type: ignore[assignment] — forces an internal TypeError
    engine = RiskEngine(_settings())

    result = engine.evaluate(db_session, _buy_signal(), portfolio, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.REJECTED
    assert "Risk evaluation error" in result.reason
