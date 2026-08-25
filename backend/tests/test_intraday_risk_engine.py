"""Tests for IntradayRiskEngine.evaluate_intraday — confirms it always runs
the full base RiskEngine first (never bypassing it) and only then layers on
the intraday-only checks (consecutive losses, cooldown, near-session-end).
Mirrors the structure of test_risk_engine.py for the base engine.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.models.enums import PositionStatus, RiskDecisionType, SignalType
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.risk.intraday_engine import IntradayRiskEngine
from app.strategies.base import StrategySignal

NOW = datetime.now(timezone.utc)
IST = ZoneInfo("Asia/Kolkata")


def _settings(**overrides) -> Settings:
    defaults = dict(
        emergency_stop=False,
        market_session_end="15:30",
        intraday_risk_max_capital_per_trade_pct=0.5,
        intraday_risk_max_simultaneous_positions=5,
        intraday_risk_max_trades_per_day=10,
        intraday_risk_max_daily_loss_pct=0.02,
        intraday_transaction_cost_percent=0.05,
        intraday_risk_max_consecutive_losses=3,
        intraday_risk_cooldown_minutes=15,
        intraday_no_entry_minutes_before_close=15,
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _portfolio(db, **overrides) -> Portfolio:
    defaults = dict(starting_capital=100_000.0, available_cash=100_000.0, current_equity=100_000.0,
                     realized_pnl=0.0, unrealized_pnl=0.0)
    defaults.update(overrides)
    p = Portfolio(**defaults)
    db.add(p)
    db.flush()
    return p


def _buy_signal(symbol="RELIANCE", price=1300.0) -> StrategySignal:
    return StrategySignal(
        symbol=symbol, signal_type=SignalType.BUY, confidence=0.8, strategy_name="INTRADAY_VWAP_MOMENTUM",
        reason="test", indicator_data={}, market_price=price, timestamp=NOW,
    )


NOON_IST = datetime(2026, 1, 5, 12, 0, tzinfo=IST)  # comfortably mid-session, far from 15:30 close


def test_buy_approved_when_no_intraday_conditions_triggered(db_session):
    portfolio = _portfolio(db_session)
    engine = IntradayRiskEngine(_settings())

    result = engine.evaluate_intraday(
        db_session, _buy_signal(price=1000.0), portfolio, NOW, is_stale=False,
        current_time_ist=NOON_IST, consecutive_losses=0, last_loss_at=None,
    )

    assert result.decision == RiskDecisionType.APPROVED
    # 50% of 100,000 equity / price 1000 = 50 shares cap.
    assert result.approved_quantity == 50


def test_base_engine_rejection_propagates_unchanged(db_session):
    """Emergency stop is a base-engine check — the intraday layer must never
    override or mask it."""
    portfolio = _portfolio(db_session)
    engine = IntradayRiskEngine(_settings(emergency_stop=True))

    result = engine.evaluate_intraday(
        db_session, _buy_signal(), portfolio, NOW, is_stale=False,
        current_time_ist=NOON_IST, consecutive_losses=0, last_loss_at=None,
    )

    assert result.decision == RiskDecisionType.REJECTED
    assert "Emergency stop" in result.reason


def test_max_consecutive_losses_blocks_new_buy(db_session):
    portfolio = _portfolio(db_session)
    engine = IntradayRiskEngine(_settings(intraday_risk_max_consecutive_losses=3))

    result = engine.evaluate_intraday(
        db_session, _buy_signal(), portfolio, NOW, is_stale=False,
        current_time_ist=NOON_IST, consecutive_losses=3, last_loss_at=None,
    )

    assert result.decision == RiskDecisionType.REJECTED
    assert "consecutive losses" in result.reason


def test_cooldown_blocks_new_buy(db_session):
    portfolio = _portfolio(db_session)
    engine = IntradayRiskEngine(_settings(intraday_risk_cooldown_minutes=15))
    last_loss_at = NOON_IST - timedelta(minutes=5)

    result = engine.evaluate_intraday(
        db_session, _buy_signal(), portfolio, NOW, is_stale=False,
        current_time_ist=NOON_IST, consecutive_losses=1, last_loss_at=last_loss_at,
    )

    assert result.decision == RiskDecisionType.REJECTED
    assert "cooldown" in result.reason.lower()


def test_near_session_end_blocks_new_buy(db_session):
    portfolio = _portfolio(db_session)
    engine = IntradayRiskEngine(_settings(intraday_no_entry_minutes_before_close=15))
    near_close = datetime(2026, 1, 5, 15, 20, tzinfo=IST)  # 10 min before 15:30 close

    result = engine.evaluate_intraday(
        db_session, _buy_signal(), portfolio, NOW, is_stale=False,
        current_time_ist=near_close, consecutive_losses=0, last_loss_at=None,
    )

    assert result.decision == RiskDecisionType.REJECTED
    assert "session end" in result.reason.lower()


def test_intraday_checks_never_apply_to_sell_signals(db_session):
    """Exits must never be blocked by the intraday-only entry checks — a
    losing streak or being near session end must not trap capital in an
    open position."""
    portfolio = _portfolio(db_session)
    db_session.add(
        Position(
            portfolio_id=portfolio.id, symbol="RELIANCE", quantity=10, entry_price=1000.0, current_price=1000.0,
            peak_price=1000.0, status=PositionStatus.OPEN,
        )
    )
    db_session.flush()
    engine = IntradayRiskEngine(_settings(intraday_risk_max_consecutive_losses=1))
    sell_signal = StrategySignal(
        symbol="RELIANCE", signal_type=SignalType.SELL, confidence=0.8, strategy_name="INTRADAY_VWAP_MOMENTUM",
        reason="test", indicator_data={}, market_price=1000.0, timestamp=NOW,
    )

    near_close = datetime(2026, 1, 5, 15, 25, tzinfo=IST)
    result = engine.evaluate_intraday(
        db_session, sell_signal, portfolio, NOW, is_stale=False,
        current_time_ist=near_close, consecutive_losses=5, last_loss_at=near_close,
    )

    assert result.decision == RiskDecisionType.APPROVED


def test_intraday_position_sizing_uses_intraday_capital_pct_not_daily(db_session):
    """The intraday cap (intraday_risk_max_capital_per_trade_pct) must be
    the one actually applied, confirming the settings copy in __init__
    took effect rather than silently falling back to the daily default."""
    portfolio = _portfolio(db_session, starting_capital=100_000.0, available_cash=100_000.0, current_equity=100_000.0)
    engine = IntradayRiskEngine(_settings(intraday_risk_max_capital_per_trade_pct=0.2))

    result = engine.evaluate_intraday(
        db_session, _buy_signal(price=1000.0), portfolio, NOW, is_stale=False,
        current_time_ist=NOON_IST, consecutive_losses=0, last_loss_at=None,
    )

    assert result.decision == RiskDecisionType.APPROVED
    # 20% of 100,000 / 1000 = 20 shares.
    assert result.approved_quantity == 20
