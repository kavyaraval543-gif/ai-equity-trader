"""Position monitor tests using a controllable fake market data provider —
deterministic price control is required to reliably trigger stop-loss/
target/trailing-stop conditions, which real live prices cannot guarantee.
"""
from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.execution.paper import PaperExecutionProvider
from app.market_data.base import Candle, MarketDataError, MarketDataProvider, PriceQuote, ProviderStatus
from app.models.enums import ExitReason, PositionStatus, TradeSide
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.trade import Trade
from app.risk.engine import RiskEngine
from app.services.position_monitor import PositionMonitor


class FakeProvider(MarketDataProvider):
    name = "fake"

    def __init__(self, prices: dict[str, float], raise_for: frozenset[str] = frozenset()) -> None:
        self.prices = prices
        self.raise_for = raise_for

    def get_latest_price(self, symbol: str) -> PriceQuote:
        if symbol in self.raise_for:
            raise MarketDataError(f"no real data available for {symbol}")
        return PriceQuote(symbol=symbol, price=self.prices[symbol], timestamp=datetime.now(timezone.utc), provider=self.name)

    def get_historical_data(self, symbol: str, interval: str, start=None, end=None) -> list[Candle]:
        raise NotImplementedError

    def get_provider_status(self) -> ProviderStatus:
        return ProviderStatus(provider=self.name, connected=True, last_successful_fetch=datetime.now(timezone.utc), detail="ok")


class FakeMarketSession:
    def __init__(self, open_: bool) -> None:
        self._open = open_

    def is_open(self, at=None) -> bool:
        return self._open


def _settings(**overrides) -> Settings:
    defaults = dict(
        risk_transaction_cost_bps=0.0,
        trailing_stop_enabled=False,
        trailing_stop_percent=1.0,
        force_close_at_session_end=False,
        emergency_stop=False,
        risk_max_trades_per_day=100,
        risk_max_daily_loss_pct=1.0,
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _portfolio(db) -> Portfolio:
    p = Portfolio(starting_capital=1_000_000.0, available_cash=1_000_000.0, current_equity=1_000_000.0,
                  realized_pnl=0.0, unrealized_pnl=0.0)
    db.add(p)
    db.flush()
    return p


def _open_position(db, portfolio, symbol="RELIANCE", entry=1000.0, stop_loss=980.0, target=1040.0) -> Position:
    pos = Position(
        portfolio_id=portfolio.id, symbol=symbol, quantity=10, entry_price=entry, current_price=entry,
        stop_loss=stop_loss, target=target, peak_price=entry, unrealized_pnl=0.0, status=PositionStatus.OPEN,
    )
    db.add(pos)
    db.flush()
    return pos


def _monitor(db, settings, prices, raise_for=frozenset(), market_open=True) -> PositionMonitor:
    return PositionMonitor(
        db,
        settings=settings,
        provider=FakeProvider(prices, raise_for),
        risk_engine=RiskEngine(settings),
        execution=PaperExecutionProvider(settings),
        market_session=FakeMarketSession(market_open),
    )


def test_updates_price_and_unrealized_pnl(db_session):
    settings = _settings()
    portfolio = _portfolio(db_session)
    position = _open_position(db_session, portfolio, entry=1000.0, stop_loss=900.0, target=1200.0)
    monitor = _monitor(db_session, settings, {"RELIANCE": 1020.0})

    result = monitor.run()

    assert result["checked"] == 1
    assert result["exits_triggered"] == 0
    assert position.current_price == 1020.0
    assert position.unrealized_pnl == pytest.approx((1020.0 - 1000.0) * 10)
    assert position.peak_price == 1020.0
    assert position.status == PositionStatus.OPEN


def test_triggers_stop_loss(db_session):
    settings = _settings()
    portfolio = _portfolio(db_session)
    position = _open_position(db_session, portfolio, entry=1000.0, stop_loss=980.0, target=1200.0)
    monitor = _monitor(db_session, settings, {"RELIANCE": 975.0})

    result = monitor.run()

    assert result["exits_triggered"] == 1
    assert position.status == PositionStatus.CLOSED
    trade = db_session.query(Trade).filter_by(symbol="RELIANCE", side=TradeSide.SELL).one()
    assert trade.exit_reason == ExitReason.STOP_LOSS
    assert trade.price == 975.0
    assert trade.realized_pnl == pytest.approx((975.0 - 1000.0) * 10)


def test_triggers_target(db_session):
    settings = _settings()
    portfolio = _portfolio(db_session)
    position = _open_position(db_session, portfolio, entry=1000.0, stop_loss=900.0, target=1050.0)
    monitor = _monitor(db_session, settings, {"RELIANCE": 1060.0})

    result = monitor.run()

    assert result["exits_triggered"] == 1
    assert position.status == PositionStatus.CLOSED
    trade = db_session.query(Trade).filter_by(symbol="RELIANCE", side=TradeSide.SELL).one()
    assert trade.exit_reason == ExitReason.TARGET_REACHED


def test_trailing_stop_triggers_after_peak_pullback(db_session):
    settings = _settings(trailing_stop_enabled=True, trailing_stop_percent=2.0)
    portfolio = _portfolio(db_session)
    position = _open_position(db_session, portfolio, entry=1000.0, stop_loss=900.0, target=2000.0)

    # First tick: price rallies to 1100, establishing a new peak.
    monitor1 = _monitor(db_session, settings, {"RELIANCE": 1100.0})
    monitor1.run()
    assert position.peak_price == 1100.0
    assert position.status == PositionStatus.OPEN

    # Second tick: price pulls back more than 2% off the peak (1100 * 0.98 = 1078).
    monitor2 = _monitor(db_session, settings, {"RELIANCE": 1070.0})
    result = monitor2.run()

    assert result["exits_triggered"] == 1
    assert position.status == PositionStatus.CLOSED
    trade = db_session.query(Trade).filter_by(symbol="RELIANCE", side=TradeSide.SELL).one()
    assert trade.exit_reason == ExitReason.TRAILING_STOP


def test_session_end_force_close(db_session):
    settings = _settings(force_close_at_session_end=True)
    portfolio = _portfolio(db_session)
    position = _open_position(db_session, portfolio, entry=1000.0, stop_loss=900.0, target=2000.0)
    monitor = _monitor(db_session, settings, {"RELIANCE": 1010.0}, market_open=False)

    result = monitor.run()

    assert result["exits_triggered"] == 1
    assert position.status == PositionStatus.CLOSED
    trade = db_session.query(Trade).filter_by(symbol="RELIANCE", side=TradeSide.SELL).one()
    assert trade.exit_reason == ExitReason.SESSION_END


def test_missing_price_handled_safely_without_crashing(db_session):
    settings = _settings()
    portfolio = _portfolio(db_session)
    position = _open_position(db_session, portfolio, entry=1000.0, stop_loss=980.0, target=1200.0)
    monitor = _monitor(db_session, settings, {}, raise_for=frozenset({"RELIANCE"}))

    result = monitor.run()

    assert result["errors"] == 1
    assert result["exits_triggered"] == 0
    assert position.status == PositionStatus.OPEN
    assert position.current_price == 1000.0  # untouched


def test_no_open_positions_is_a_noop(db_session):
    settings = _settings()
    _portfolio(db_session)
    monitor = _monitor(db_session, settings, {})

    result = monitor.run()

    assert result == {"checked": 0, "exits_triggered": 0, "errors": 0, "timestamp": result["timestamp"]}
