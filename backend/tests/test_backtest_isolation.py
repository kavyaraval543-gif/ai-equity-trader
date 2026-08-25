"""Verifies a backtest never touches the live autonomous-trading tables —
Portfolio, Position, Trade, AutonomousState — only the separate
backtest_runs/backtest_trades tables.
"""
from datetime import datetime, timedelta, timezone

from app.backtesting.engine import BacktestEngine
from app.core.config import Settings
from app.models.autonomous_state import AutonomousState
from app.models.backtest import BacktestRun, BacktestTrade
from app.models.enums import AutonomousTradingState, PositionStatus, TradeSide
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.trade import Trade
from app.strategies.sma_crossover import SmaCrossoverStrategy
from tests.test_backtest_engine import BASE_DATE, BUY_SELL_CLOSES, FakeHistoricalProvider, _candles


def _seed_live_state(db):
    """A running live system: an active portfolio, an open position, a
    recorded trade, and autonomous trading RUNNING."""
    portfolio = Portfolio(
        starting_capital=1_000_000.0, available_cash=986_000.0, current_equity=1_000_014.0,
        realized_pnl=500.0, unrealized_pnl=14.0,
    )
    db.add(portfolio)
    db.flush()
    db.add(
        Position(
            portfolio_id=portfolio.id, symbol="RELIANCE", quantity=10, entry_price=1400.0, current_price=1401.4,
            peak_price=1401.4, unrealized_pnl=14.0, status=PositionStatus.OPEN,
        )
    )
    db.add(
        Trade(
            portfolio_id=portfolio.id, symbol="TCS", side=TradeSide.BUY, quantity=5, price=2300.0,
            transaction_cost=1.15, strategy_name="SMA_CROSSOVER", timestamp=datetime.now(timezone.utc),
        )
    )
    db.add(AutonomousState(state=AutonomousTradingState.RUNNING, reason="Started via API."))
    db.commit()
    return portfolio.id


def _snapshot(db) -> dict:
    return {
        "portfolios": [(p.id, p.available_cash, p.current_equity, p.realized_pnl) for p in db.query(Portfolio).all()],
        "positions": [(p.id, p.symbol, p.status, p.quantity) for p in db.query(Position).all()],
        "trades": [(t.id, t.symbol, t.side, t.quantity) for t in db.query(Trade).all()],
        "autonomous_state": [(s.id, s.state) for s in db.query(AutonomousState).all()],
    }


def _run_and_persist_backtest(db) -> BacktestRun:
    candles = _candles(BUY_SELL_CLOSES)
    engine = BacktestEngine(
        provider=FakeHistoricalProvider(candles),
        strategy=SmaCrossoverStrategy(short_window=3, long_window=5),
        settings=Settings(_env_file=None),
    )
    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.1)

    run = BacktestRun(
        symbol=result.symbol, start_date=BASE_DATE, end_date=BASE_DATE + timedelta(days=23),
        starting_capital=result.starting_capital, ending_capital=result.ending_capital,
        total_return_pct=result.total_return_pct, total_trades=result.total_trades,
        winning_trades=result.winning_trades, losing_trades=result.losing_trades, win_rate=result.win_rate,
        max_drawdown_pct=result.max_drawdown_pct, buy_hold_return_pct=result.buy_hold_return_pct,
        transaction_cost_percent=result.transaction_cost_percent, strategy_name=result.strategy_name,
    )
    db.add(run)
    db.flush()
    for t in result.trades:
        db.add(
            BacktestTrade(
                backtest_run_id=run.id, symbol=result.symbol, side=t.side, quantity=t.quantity,
                price=t.price, transaction_cost=t.transaction_cost, realized_pnl=t.realized_pnl,
                timestamp=t.timestamp,
            )
        )
    db.commit()
    return run


def test_backtest_does_not_modify_live_portfolio_position_or_trades(db_session):
    _seed_live_state(db_session)
    before = _snapshot(db_session)

    _run_and_persist_backtest(db_session)

    after = _snapshot(db_session)
    assert before == after


def test_backtest_results_land_only_in_backtest_tables(db_session):
    _seed_live_state(db_session)

    run = _run_and_persist_backtest(db_session)

    assert db_session.query(BacktestRun).count() == 1
    assert db_session.query(BacktestTrade).filter_by(backtest_run_id=run.id).count() == run.total_trades * 2
    # Live tables still show exactly the seeded rows — nothing extra appeared.
    assert db_session.query(Portfolio).count() == 1
    assert db_session.query(Position).count() == 1
    assert db_session.query(Trade).count() == 1


def test_backtest_engine_never_imports_live_trading_models():
    """A structural guard: the engine module's own source must not reference
    the live Portfolio/Position/Trade/AutonomousState models at all."""
    import inspect

    from app.backtesting import engine as engine_module

    source = inspect.getsource(engine_module)
    for forbidden in ("app.models.portfolio", "app.models.position", "app.models.trade", "app.models.autonomous_state"):
        assert forbidden not in source
