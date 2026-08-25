from app.core.config import Settings
from app.models.enums import AutonomousTradingState, PositionStatus
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.signal import Signal
from app.models.trade import Trade
from app.models.enums import SignalType, TradeSide
from app.services import autonomous_control_service
from app.services.startup_recovery import run_startup_recovery
from datetime import datetime, timezone


def _settings(**overrides) -> Settings:
    defaults = dict(starting_capital=1_000_000.0)
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def test_fresh_database_creates_default_portfolio_and_stopped_state(db_session):
    result = run_startup_recovery(db_session, _settings())

    assert result["autonomous_state"] == AutonomousTradingState.STOPPED
    assert result["open_position_count"] == 0
    assert result["portfolio_equity"] == 1_000_000.0


def test_open_positions_reload_and_equity_recalculates(db_session):
    portfolio = Portfolio(
        starting_capital=1_000_000.0, available_cash=986_000.0, current_equity=1_000_000.0,
        realized_pnl=0.0, unrealized_pnl=0.0,
    )
    db_session.add(portfolio)
    db_session.flush()
    db_session.add(
        Position(
            portfolio_id=portfolio.id, symbol="RELIANCE", quantity=10, entry_price=1400.0, current_price=1420.0,
            peak_price=1420.0, unrealized_pnl=200.0, status=PositionStatus.OPEN,
        )
    )
    db_session.flush()

    result = run_startup_recovery(db_session, _settings())

    assert result["open_position_count"] == 1
    # equity = available_cash (986,000) + market value (10 * 1420 = 14,200)
    assert result["portfolio_equity"] == 986_000.0 + 14_200.0


def test_previously_running_state_survives_restart(db_session):
    autonomous_control_service.start(db_session, _settings())

    result = run_startup_recovery(db_session, _settings())

    assert result["autonomous_state"] == AutonomousTradingState.RUNNING


def test_recovery_does_not_create_new_trades_or_positions(db_session):
    portfolio = Portfolio(
        starting_capital=1_000_000.0, available_cash=1_000_000.0, current_equity=1_000_000.0,
        realized_pnl=0.0, unrealized_pnl=0.0,
    )
    db_session.add(portfolio)
    db_session.flush()
    db_session.add(
        Signal(
            symbol="RELIANCE", signal_type=SignalType.BUY, confidence=0.9, strategy_name="SMA_CROSSOVER",
            reason="pre-restart signal", indicator_data={}, market_price=1300.0,
            timestamp=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    trades_before = db_session.query(Trade).count()
    positions_before = db_session.query(Position).count()

    run_startup_recovery(db_session, _settings())

    assert db_session.query(Trade).count() == trades_before == 0
    assert db_session.query(Position).count() == positions_before == 0


def test_recovery_is_idempotent_across_multiple_calls(db_session):
    settings = _settings()
    first = run_startup_recovery(db_session, settings)
    second = run_startup_recovery(db_session, settings)

    assert first["portfolio_equity"] == second["portfolio_equity"]
    assert first["autonomous_state"] == second["autonomous_state"]
