"""Runs the same historical data through several strategy configurations
for direct comparison, and (optionally) across all configured stocks
independently. Each configuration/stock combination is its own isolated
simulation — no shared state, no cross-strategy or cross-stock influence,
no combined portfolio.
"""
from datetime import date

from app.backtesting.engine import BacktestEngine
from app.backtesting.results import BacktestResult
from app.market_data.base import MarketDataProvider
from app.market_data.factory import get_market_data_provider
from app.market_data.symbols import DEFAULT_SYMBOLS
from app.strategies.base import BaseStrategy
from app.strategies.rsi import RsiStrategy
from app.strategies.sma_crossover import SmaCrossoverStrategy


def default_comparison_strategies() -> list[BaseStrategy]:
    """The fixed set of configurations Phase 4B compares."""
    return [
        SmaCrossoverStrategy(short_window=5, long_window=20),
        SmaCrossoverStrategy(short_window=10, long_window=30),
        SmaCrossoverStrategy(short_window=20, long_window=50),
        SmaCrossoverStrategy(short_window=50, long_window=200),
        RsiStrategy(period=14, oversold=30.0, overbought=70.0),
    ]


def run_comparison(
    symbol: str,
    start_date: date,
    end_date: date,
    starting_capital: float,
    transaction_cost_percent: float,
    strategies: list[BaseStrategy] | None = None,
    provider: MarketDataProvider | None = None,
) -> list[BacktestResult]:
    """Every strategy configuration against the SAME stock, date range,
    starting capital, and transaction cost. Fetches the underlying candle
    data once — sized for whichever configuration needs the most warm-up —
    and reuses it across every configuration instead of fetching once per
    configuration."""
    strategies = strategies or default_comparison_strategies()
    provider = provider or get_market_data_provider()
    symbol = symbol.upper()

    widest_engine = BacktestEngine(provider=provider, strategy=max(strategies, key=lambda s: s.warmup_period))
    candles = widest_engine.fetch_candles(symbol, start_date, end_date)

    results = []
    for strategy in strategies:
        engine = BacktestEngine(provider=provider, strategy=strategy)
        result = engine.run_with_candles(
            symbol, candles, start_date, end_date, starting_capital, transaction_cost_percent
        )
        results.append(result)
    return results


def run_multi_stock_comparison(
    start_date: date,
    end_date: date,
    starting_capital: float,
    transaction_cost_percent: float,
    strategies: list[BaseStrategy] | None = None,
    provider: MarketDataProvider | None = None,
    symbols: list[str] | None = None,
) -> dict[str, list[BacktestResult]]:
    """Runs the comparison independently for every configured stock — each
    stock gets its own fresh `starting_capital`, never pooled with another
    symbol's results. Returns {symbol: [BacktestResult, ...]}; averaging
    across symbols is the caller's job (it needs DB-persisted run ids too)."""
    strategies = strategies or default_comparison_strategies()
    provider = provider or get_market_data_provider()
    symbols = symbols or DEFAULT_SYMBOLS

    return {
        symbol: run_comparison(
            symbol, start_date, end_date, starting_capital, transaction_cost_percent, strategies, provider
        )
        for symbol in symbols
    }
