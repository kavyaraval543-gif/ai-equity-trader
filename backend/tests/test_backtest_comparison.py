"""Tests for app/backtesting/comparison.py — the pure orchestration layer
(no DB, no API). API-level ranking/persistence behavior is covered in
tests/test_backtest_comparison_api.py.
"""
from datetime import date, datetime, timedelta, timezone

from app.backtesting.comparison import default_comparison_strategies, run_comparison, run_multi_stock_comparison
from app.market_data.base import Candle, MarketDataProvider, PriceQuote, ProviderStatus
from app.market_data.symbols import DEFAULT_SYMBOLS

BASE_DATE = date(2025, 1, 1)


def _candles(closes: list[float]) -> list[Candle]:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(timestamp=base + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1000)
        for i, c in enumerate(closes)
    ]


# Enough bars (250) to satisfy even SMA(50,200)'s warm-up with room to spare,
# with a couple of clear moves so strategies actually trade.
def _long_series() -> list[float]:
    closes = [100.0] * 220
    closes += [130.0] * 15   # a rally
    closes += [90.0] * 15    # a decline
    return closes


class FakeProvider(MarketDataProvider):
    name = "fake"

    def __init__(self, per_symbol_closes: dict[str, list[float]]) -> None:
        self._data = {sym: _candles(closes) for sym, closes in per_symbol_closes.items()}
        self.fetch_calls: list[str] = []

    def get_latest_price(self, symbol: str) -> PriceQuote:  # pragma: no cover - unused
        raise NotImplementedError

    def get_historical_data(self, symbol: str, interval: str, start=None, end=None) -> list[Candle]:
        self.fetch_calls.append(symbol)
        return list(self._data[symbol])

    def get_provider_status(self) -> ProviderStatus:  # pragma: no cover - unused
        return ProviderStatus(provider=self.name, connected=True, last_successful_fetch=None, detail="ok")


def test_comparison_runs_all_five_default_configurations():
    provider = FakeProvider({"RELIANCE": _long_series()})

    results = run_comparison(
        "RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=249), 100_000.0, 0.1, provider=provider
    )

    assert len(results) == 5
    labels = {(r.strategy_name, tuple(sorted(r.strategy_params.items()))) for r in results}
    assert len(labels) == 5, "each configuration must be distinct"
    assert any(r.strategy_name == "RSI" for r in results)
    assert sum(1 for r in results if r.strategy_name == "SMA_CROSSOVER") == 4


def test_comparison_buy_hold_return_is_identical_across_all_strategies():
    """Buy & hold for the same stock/range/capital/cost cannot depend on
    which strategy happened to be simulated alongside it."""
    provider = FakeProvider({"RELIANCE": _long_series()})

    results = run_comparison(
        "RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=249), 100_000.0, 0.1, provider=provider
    )

    buy_hold_values = {round(r.buy_hold_return_pct, 8) for r in results}
    assert len(buy_hold_values) == 1


def test_comparison_fetches_candles_once_not_once_per_strategy():
    provider = FakeProvider({"RELIANCE": _long_series()})

    run_comparison("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=249), 100_000.0, 0.1, provider=provider)

    assert provider.fetch_calls == ["RELIANCE"]


def test_comparison_applies_transaction_costs_consistently_across_strategies():
    provider_free = FakeProvider({"RELIANCE": _long_series()})
    provider_cost = FakeProvider({"RELIANCE": _long_series()})

    free_results = run_comparison(
        "RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=249), 100_000.0, 0.0, provider=provider_free
    )
    cost_results = run_comparison(
        "RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=249), 100_000.0, 1.0, provider=provider_cost
    )

    for free, costly in zip(free_results, cost_results):
        assert free.strategy_name == costly.strategy_name
        assert free.strategy_params == costly.strategy_params
        if free.total_trades > 0:
            # Every trade in the costly run must carry a non-zero transaction cost.
            assert all(t.transaction_cost > 0 for t in costly.trades)
            assert all(t.transaction_cost == 0 for t in free.trades)


def test_multi_stock_comparison_runs_all_five_symbols_independently():
    per_symbol = {sym: _long_series() for sym in DEFAULT_SYMBOLS}
    provider = FakeProvider(per_symbol)

    by_symbol = run_multi_stock_comparison(
        BASE_DATE, BASE_DATE + timedelta(days=249), 100_000.0, 0.1, provider=provider
    )

    assert set(by_symbol.keys()) == set(DEFAULT_SYMBOLS)
    for symbol, results in by_symbol.items():
        assert len(results) == 5
        assert all(r.symbol == symbol for r in results)


def test_multi_stock_comparison_isolation_different_data_yields_different_results():
    """One stock's price action must not leak into another's results —
    each symbol gets its own independent simulation."""
    per_symbol = {sym: _long_series() for sym in DEFAULT_SYMBOLS}
    # Make one symbol's data flat (no strategy trades, 0% buy & hold return)
    # while the others keep the rally/decline pattern.
    per_symbol["TCS"] = [100.0] * 250
    provider = FakeProvider(per_symbol)

    # Zero transaction cost here so flat-price buy & hold is unambiguously
    # 0% — transaction cost's effect on buy & hold is covered separately.
    by_symbol = run_multi_stock_comparison(
        BASE_DATE, BASE_DATE + timedelta(days=249), 100_000.0, 0.0, provider=provider
    )

    tcs_results = by_symbol["TCS"]
    reliance_results = by_symbol["RELIANCE"]

    assert all(r.total_trades == 0 for r in tcs_results)
    assert all(r.buy_hold_return_pct == 0.0 for r in tcs_results)
    # RELIANCE had real price movement, so at least one config should differ.
    assert any(r.buy_hold_return_pct != 0.0 for r in reliance_results)


def test_default_comparison_strategies_cover_the_required_configurations():
    strategies = default_comparison_strategies()
    sma_configs = {(s.short_window, s.long_window) for s in strategies if s.name == "SMA_CROSSOVER"}

    assert sma_configs == {(5, 20), (10, 30), (20, 50), (50, 200)}
    assert any(s.name == "RSI" for s in strategies)
