"""Regression coverage for the DAILY vs INTRADAY portfolio isolation added
in Phase 5. Before a second portfolio (PortfolioKind.INTRADAY) could ever
exist, several checks were only ever exercised against a single portfolio
and were missing portfolio_id scoping — harmless until a second portfolio
existed, but each is a real bug once one does:

  - RiskEngine's duplicate-position and max-simultaneous-positions checks
    (app/risk/engine.py) queried Position across ALL portfolios.
  - PaperExecutionProvider._execute_sell's position lookup (app/execution/
    paper.py) queried Position across ALL portfolios — would raise
    MultipleResultsFound the moment the same symbol had an open position in
    both portfolios simultaneously.
  - PaperExecutionProvider.update_position_prices (app/execution/paper.py)
    marked-to-market every open position for a symbol across ALL
    portfolios, so one portfolio's price fetch cadence could silently
    touch another portfolio's position (including its peak_price, which
    feeds trailing-stop calculations).

These tests build the exact scenario each bug needed (the same symbol held
open in both portfolios at once) and confirm each is now correctly scoped.
"""
from datetime import datetime, timezone

from app.core.config import Settings
from app.models.enums import PortfolioKind, PositionStatus, RiskDecisionType, SignalType
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.execution.paper import PaperExecutionProvider
from app.risk.engine import RiskEngine
from app.risk.schemas import RiskDecisionResult
from app.services.portfolio_service import get_or_create_intraday_portfolio, get_or_create_portfolio
from app.strategies.base import StrategySignal

NOW = datetime.now(timezone.utc)


def _portfolio(db, kind: PortfolioKind, **overrides) -> Portfolio:
    defaults = dict(starting_capital=100_000.0, available_cash=100_000.0, current_equity=100_000.0,
                     realized_pnl=0.0, unrealized_pnl=0.0, kind=kind)
    defaults.update(overrides)
    p = Portfolio(**defaults)
    db.add(p)
    db.flush()
    return p


def _open_position(db, portfolio: Portfolio, symbol="RELIANCE", **overrides) -> Position:
    defaults = dict(portfolio_id=portfolio.id, symbol=symbol, quantity=10, entry_price=1000.0, current_price=1000.0,
                     peak_price=1000.0, status=PositionStatus.OPEN)
    defaults.update(overrides)
    p = Position(**defaults)
    db.add(p)
    db.flush()
    return p


def test_get_or_create_portfolio_returns_separate_rows_per_kind(db_session):
    daily = get_or_create_portfolio(db_session, kind=PortfolioKind.DAILY)
    intraday = get_or_create_intraday_portfolio(db_session)

    assert daily.id != intraday.id
    assert daily.kind == PortfolioKind.DAILY
    assert intraday.kind == PortfolioKind.INTRADAY

    # Idempotent per kind — calling again returns the SAME row, not a third one.
    daily_again = get_or_create_portfolio(db_session, kind=PortfolioKind.DAILY)
    assert daily_again.id == daily.id


def test_duplicate_position_check_is_scoped_to_its_own_portfolio(db_session):
    """An open RELIANCE position in the DAILY portfolio must not block a
    fresh BUY of RELIANCE in the INTRADAY portfolio."""
    daily = _portfolio(db_session, PortfolioKind.DAILY)
    intraday = _portfolio(db_session, PortfolioKind.INTRADAY)
    _open_position(db_session, daily, symbol="RELIANCE")

    engine = RiskEngine(Settings(_env_file=None))
    buy_signal = StrategySignal(
        symbol="RELIANCE", signal_type=SignalType.BUY, confidence=0.8, strategy_name="INTRADAY_VWAP_MOMENTUM",
        reason="test", indicator_data={}, market_price=1000.0, timestamp=NOW,
    )

    result = engine.evaluate(db_session, buy_signal, intraday, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.APPROVED


def test_max_simultaneous_positions_check_is_scoped_to_its_own_portfolio(db_session):
    """Two open positions in the DAILY portfolio must not count against the
    INTRADAY portfolio's own (much lower) simultaneous-position cap."""
    daily = _portfolio(db_session, PortfolioKind.DAILY)
    intraday = _portfolio(db_session, PortfolioKind.INTRADAY)
    _open_position(db_session, daily, symbol="TCS")
    _open_position(db_session, daily, symbol="INFY")

    engine = RiskEngine(Settings(_env_file=None, risk_max_simultaneous_positions=1))
    buy_signal = StrategySignal(
        symbol="RELIANCE", signal_type=SignalType.BUY, confidence=0.8, strategy_name="INTRADAY_VWAP_MOMENTUM",
        reason="test", indicator_data={}, market_price=1000.0, timestamp=NOW,
    )

    result = engine.evaluate(db_session, buy_signal, intraday, NOW, is_stale=False)

    assert result.decision == RiskDecisionType.APPROVED


def test_sell_execution_closes_the_correct_portfolios_position_only(db_session):
    """The historical bug: the same symbol open in both portfolios at once
    used to raise MultipleResultsFound (an unscoped .scalar_one_or_none()
    query). This is the exact reachability scenario."""
    daily = _portfolio(db_session, PortfolioKind.DAILY)
    intraday = _portfolio(db_session, PortfolioKind.INTRADAY)
    daily_position = _open_position(db_session, daily, symbol="RELIANCE", quantity=10, entry_price=1000.0)
    intraday_position = _open_position(db_session, intraday, symbol="RELIANCE", quantity=5, entry_price=1200.0)

    provider = PaperExecutionProvider(Settings(_env_file=None, risk_transaction_cost_bps=0.0))
    sell_signal = StrategySignal(
        symbol="RELIANCE", signal_type=SignalType.SELL, confidence=0.8, strategy_name="INTRADAY_VWAP_MOMENTUM",
        reason="test", indicator_data={}, market_price=1300.0, timestamp=NOW,
    )
    approved = RiskDecisionResult(
        signal=sell_signal, decision=RiskDecisionType.APPROVED, reason="test", approved_quantity=5
    )

    trade = provider.execute_approved_signal(db_session, approved, intraday)  # must not raise

    assert trade.portfolio_id == intraday.id
    assert intraday_position.status == PositionStatus.CLOSED
    # The daily portfolio's own RELIANCE position must be completely untouched.
    assert daily_position.status == PositionStatus.OPEN
    assert daily_position.quantity == 10


def test_mark_to_market_scoped_to_portfolio_does_not_touch_other_portfolios_position(db_session):
    daily = _portfolio(db_session, PortfolioKind.DAILY)
    intraday = _portfolio(db_session, PortfolioKind.INTRADAY)
    daily_position = _open_position(db_session, daily, symbol="RELIANCE", current_price=1000.0, peak_price=1000.0)
    intraday_position = _open_position(db_session, intraday, symbol="RELIANCE", current_price=1000.0, peak_price=1000.0)

    provider = PaperExecutionProvider(Settings(_env_file=None))
    # A price fetched for the intraday cycle must only mark the intraday position.
    provider.update_position_prices(db_session, {"RELIANCE": 1500.0}, portfolio_id=intraday.id)

    assert intraday_position.current_price == 1500.0
    assert intraday_position.peak_price == 1500.0
    assert daily_position.current_price == 1000.0
    assert daily_position.peak_price == 1000.0


def test_mark_to_market_with_no_portfolio_id_updates_across_all_portfolios(db_session):
    """Backward-compatible default: omitting portfolio_id preserves the
    original (pre-Phase-5) unscoped behavior for any caller that genuinely
    wants it (there is none in this codebase today, but the option is
    intentional, not an oversight)."""
    daily = _portfolio(db_session, PortfolioKind.DAILY)
    intraday = _portfolio(db_session, PortfolioKind.INTRADAY)
    daily_position = _open_position(db_session, daily, symbol="RELIANCE", current_price=1000.0, peak_price=1000.0)
    intraday_position = _open_position(db_session, intraday, symbol="RELIANCE", current_price=1000.0, peak_price=1000.0)

    provider = PaperExecutionProvider(Settings(_env_file=None))
    provider.update_position_prices(db_session, {"RELIANCE": 1500.0})  # no portfolio_id -> unscoped

    assert daily_position.current_price == 1500.0
    assert intraday_position.current_price == 1500.0
