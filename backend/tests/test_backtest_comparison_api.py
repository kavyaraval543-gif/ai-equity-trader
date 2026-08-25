"""API-level tests for the comparison endpoints: ranking behavior, the
synthetic Buy & Hold row, and end-to-end isolation from the live trading
tables when driven through real HTTP requests (not just direct engine
calls, which test_backtest_isolation.py already covers)."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.database.session import get_db
from app.main import app
from app.market_data.base import Candle, MarketDataProvider, PriceQuote, ProviderStatus
from app.models.autonomous_state import AutonomousState
from app.models.enums import AutonomousTradingState, PositionStatus, TradeSide
from app.models.portfolio import Portfolio
from app.models.position import Position
from app.models.trade import Trade

BASE_DATE = date(2025, 1, 1)
END_DATE = BASE_DATE + timedelta(days=249)


def _candles(closes: list[float]) -> list[Candle]:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(timestamp=base + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1000)
        for i, c in enumerate(closes)
    ]


def _long_series() -> list[float]:
    closes = [100.0] * 220
    closes += [130.0] * 15
    closes += [90.0] * 15
    return closes


class FakeProvider(MarketDataProvider):
    name = "fake"

    def __init__(self, per_symbol_closes: dict[str, list[float]]) -> None:
        self._data = {sym: _candles(closes) for sym, closes in per_symbol_closes.items()}

    def get_latest_price(self, symbol: str) -> PriceQuote:  # pragma: no cover - unused
        raise NotImplementedError

    def get_historical_data(self, symbol: str, interval: str, start=None, end=None) -> list[Candle]:
        return list(self._data[symbol])

    def get_provider_status(self) -> ProviderStatus:  # pragma: no cover - unused
        return ProviderStatus(provider=self.name, connected=True, last_successful_fetch=None, detail="ok")


@pytest.fixture()
def client(db_session):
    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _seed_live_state(db):
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


def test_compare_endpoint_ranks_results_by_return_descending(client, monkeypatch):
    provider = FakeProvider({"RELIANCE": _long_series()})
    monkeypatch.setattr("app.backtesting.comparison.get_market_data_provider", lambda: provider)

    resp = client.post(
        "/api/v1/backtests/compare",
        json={
            "symbol": "RELIANCE",
            "start_date": BASE_DATE.isoformat(),
            "end_date": END_DATE.isoformat(),
            "starting_capital": 100_000.0,
            "transaction_cost_percent": 0.1,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    returns = [r["total_return_pct"] for r in body["results"]]
    assert returns == sorted(returns, reverse=True)


def test_compare_endpoint_includes_buy_and_hold_row(client, monkeypatch):
    provider = FakeProvider({"RELIANCE": _long_series()})
    monkeypatch.setattr("app.backtesting.comparison.get_market_data_provider", lambda: provider)

    resp = client.post(
        "/api/v1/backtests/compare",
        json={
            "symbol": "RELIANCE",
            "start_date": BASE_DATE.isoformat(),
            "end_date": END_DATE.isoformat(),
            "starting_capital": 100_000.0,
            "transaction_cost_percent": 0.1,
        },
    )

    body = resp.json()
    assert len(body["results"]) == 6  # 4 SMA configs + RSI + Buy & Hold
    buy_hold_rows = [r for r in body["results"] if r["strategy_name"] == "BUY_AND_HOLD"]
    assert len(buy_hold_rows) == 1
    assert buy_hold_rows[0]["backtest_run_id"] is None  # not persisted as a fake strategy run
    assert "disclaimer" in body and "historical" in body["disclaimer"].lower()


def test_compare_endpoint_does_not_touch_live_trading_tables(client, db_session, monkeypatch):
    _seed_live_state(db_session)
    before = {
        "portfolios": db_session.query(Portfolio).count(),
        "positions": db_session.query(Position).count(),
        "trades": db_session.query(Trade).count(),
    }

    provider = FakeProvider({"RELIANCE": _long_series()})
    monkeypatch.setattr("app.backtesting.comparison.get_market_data_provider", lambda: provider)
    resp = client.post(
        "/api/v1/backtests/compare",
        json={
            "symbol": "RELIANCE",
            "start_date": BASE_DATE.isoformat(),
            "end_date": END_DATE.isoformat(),
            "starting_capital": 100_000.0,
            "transaction_cost_percent": 0.1,
        },
    )
    assert resp.status_code == 200

    after = {
        "portfolios": db_session.query(Portfolio).count(),
        "positions": db_session.query(Position).count(),
        "trades": db_session.query(Trade).count(),
    }
    assert before == after


def test_multi_stock_compare_endpoint_averages_and_ranks(client, monkeypatch):
    from app.market_data.symbols import DEFAULT_SYMBOLS

    per_symbol = {sym: _long_series() for sym in DEFAULT_SYMBOLS}
    provider = FakeProvider(per_symbol)
    monkeypatch.setattr("app.backtesting.comparison.get_market_data_provider", lambda: provider)

    resp = client.post(
        "/api/v1/backtests/compare-multi-stock",
        json={
            "start_date": BASE_DATE.isoformat(),
            "end_date": END_DATE.isoformat(),
            "starting_capital": 100_000.0,
            "transaction_cost_percent": 0.1,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["averages"]) == 5  # 4 SMA configs + RSI (buy & hold isn't a "strategy" to average here)
    for avg in body["averages"]:
        assert len(avg["per_stock"]) == 5  # every one of the 5 configured stocks
        assert {r["symbol"] for r in avg["per_stock"]} == set(DEFAULT_SYMBOLS)

    avg_returns = [a["avg_return_pct"] for a in body["averages"]]
    assert avg_returns == sorted(avg_returns, reverse=True)
