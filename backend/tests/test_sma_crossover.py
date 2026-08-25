"""Strategy logic tested against constructed candle sequences with a known,
deterministic crossover — this validates the SMA math itself. It is
separate from the live system, which only ever trades on real fetched
market data (see app/market_data/yahoo_provider.py)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.market_data.base import Candle
from app.models.enums import SignalType
from app.strategies.sma_crossover import SmaCrossoverStrategy


def _candles(closes: list[float]) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(timestamp=base + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1000)
        for i, c in enumerate(closes)
    ]


def test_sma_crossover_buy_signal():
    strategy = SmaCrossoverStrategy(short_window=3, long_window=5)
    closes = [100] * 9 + [130]
    signal = strategy.generate_signal("TEST", _candles(closes))

    assert signal.signal_type == SignalType.BUY
    assert signal.strategy_name == "SMA_CROSSOVER"
    assert signal.market_price == 130
    assert signal.indicator_data["sma_short"] > signal.indicator_data["sma_long"]
    assert 0 < signal.confidence <= 0.95


def test_sma_crossover_sell_signal():
    strategy = SmaCrossoverStrategy(short_window=3, long_window=5)
    closes = [100] * 9 + [70]
    signal = strategy.generate_signal("TEST", _candles(closes))

    assert signal.signal_type == SignalType.SELL
    assert signal.indicator_data["sma_short"] < signal.indicator_data["sma_long"]


def test_sma_crossover_hold_when_no_crossover():
    strategy = SmaCrossoverStrategy(short_window=3, long_window=5)
    closes = [100] * 10
    signal = strategy.generate_signal("TEST", _candles(closes))

    assert signal.signal_type == SignalType.HOLD


def test_sma_crossover_hold_on_insufficient_history():
    strategy = SmaCrossoverStrategy(short_window=10, long_window=30)
    signal = strategy.generate_signal("TEST", _candles([100, 101, 102]))

    assert signal.signal_type == SignalType.HOLD
    assert "Insufficient history" in signal.reason
    assert signal.confidence == 0.0


def test_sma_configurable_windows_are_recorded():
    strategy = SmaCrossoverStrategy(short_window=5, long_window=20)

    assert strategy.short_window == 5
    assert strategy.long_window == 20
    assert strategy.warmup_period == 20
    assert strategy.get_params() == {"short_window": 5, "long_window": 20}


def test_sma_defaults_come_from_settings_when_unspecified():
    strategy = SmaCrossoverStrategy()

    assert strategy.short_window > 0
    assert strategy.long_window > strategy.short_window


@pytest.mark.parametrize("short_window,long_window", [(10, 10), (30, 10), (20, 5)])
def test_sma_fast_period_must_be_less_than_slow_period(short_window, long_window):
    with pytest.raises(ValueError, match="must be less than"):
        SmaCrossoverStrategy(short_window=short_window, long_window=long_window)


@pytest.mark.parametrize("short_window,long_window", [(0, 20), (-5, 20), (5, 0), (5, -20)])
def test_sma_windows_must_be_positive(short_window, long_window):
    with pytest.raises(ValueError):
        SmaCrossoverStrategy(short_window=short_window, long_window=long_window)
