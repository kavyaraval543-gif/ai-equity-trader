"""Tests for IntradayVwapMomentumStrategy — the one new intraday strategy.
Uses small, hand-derived windows (fast_ema=2, slow_ema=3, rsi_period=3,
volume_avg_window=3) rather than the real configured defaults, so every
EMA/RSI/VWAP value in these scenarios can be computed by hand and asserted
exactly — the same approach test_backtest_engine.py uses for the daily SMA
strategy. The live/production defaults are separately exercised against
real market data (see the manual verification in this session); these
tests pin down the entry/exit rule *logic* deterministically.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.market_data.base import Candle
from app.models.enums import SignalType
from app.strategies.intraday_vwap_momentum import IntradayVwapMomentumStrategy

BASE = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)


def _candle(i: int, close: float, volume: float, day_offset: int = 0) -> Candle:
    ts = BASE + timedelta(days=day_offset, minutes=5 * i)
    return Candle(timestamp=ts, open=close, high=close, low=close, close=close, volume=volume)


# Hand-derived scenario (see PR discussion / commit message for the by-hand
# EMA/RSI/VWAP derivation): a flat run at 100, a small dip to 99, then a
# recovery to 100 with a volume spike — produces a fresh EMA(2/3) crossover
# up, RSI(3)=50, VWAP≈99.89 (close 100 is above it), and volume confirmed,
# all landing on the SAME final bar (index 4).
BUY_CLOSES = [100.0, 100.0, 100.0, 99.0, 100.0]
BUY_VOLUMES_WITH_SPIKE = [1000.0, 1000.0, 1000.0, 1000.0, 5000.0]
BUY_VOLUMES_FLAT = [1000.0] * 5


def _strategy(**overrides) -> IntradayVwapMomentumStrategy:
    defaults = dict(fast_ema=2, slow_ema=3, rsi_period=3, rsi_min=40.0, rsi_max=90.0, volume_avg_window=3, volume_multiplier=1.0)
    defaults.update(overrides)
    return IntradayVwapMomentumStrategy(**defaults)


def _candles(closes, volumes, day_offset: int = 0) -> list[Candle]:
    return [_candle(i, c, v, day_offset) for i, (c, v) in enumerate(zip(closes, volumes))]


def test_insufficient_history_returns_hold():
    strategy = _strategy()
    candles = _candles(BUY_CLOSES[:4], BUY_VOLUMES_WITH_SPIKE[:4])  # warmup_period is 5; only 4 given

    signal = strategy.generate_signal("RELIANCE", candles)

    assert signal.signal_type == SignalType.HOLD
    assert "Insufficient history" in signal.reason
    assert signal.confidence == 0.0


def test_all_conditions_aligned_produces_buy():
    strategy = _strategy()
    candles = _candles(BUY_CLOSES, BUY_VOLUMES_WITH_SPIKE)

    signal = strategy.generate_signal("RELIANCE", candles)

    assert signal.signal_type == SignalType.BUY
    assert signal.indicator_data["rsi"] == pytest.approx(50.0, abs=0.5)
    assert signal.indicator_data["above_vwap"] is True
    assert signal.indicator_data["volume_confirmed"] is True
    # Confidence is the documented rule-derived sum, not an arbitrary number.
    assert 0.5 < signal.confidence <= 0.95


def test_buy_blocked_when_volume_not_confirmed():
    """Same price path as the BUY case, but without the volume spike —
    trend + VWAP + RSI all still align, but volume confirmation fails, so
    the strategy must not fire a BUY."""
    strategy = _strategy()
    candles = _candles(BUY_CLOSES, BUY_VOLUMES_FLAT)

    signal = strategy.generate_signal("RELIANCE", candles)

    assert signal.indicator_data["volume_confirmed"] is False
    assert signal.signal_type == SignalType.HOLD


def test_buy_blocked_when_rsi_outside_band():
    """Same price/volume path, but a tighter RSI band that excludes the
    computed RSI(3)=50 — the strategy must not fire despite the crossover."""
    strategy = _strategy(rsi_min=60.0, rsi_max=90.0)
    candles = _candles(BUY_CLOSES, BUY_VOLUMES_WITH_SPIKE)

    signal = strategy.generate_signal("RELIANCE", candles)

    assert signal.indicator_data["rsi_in_band"] is False
    assert signal.signal_type == SignalType.HOLD


def test_sell_on_trend_reversal():
    strategy = _strategy()
    # Rises to build an uptrend, then a hard drop reverses the crossover.
    closes = [100.0, 100.0, 100.0, 100.0, 105.0, 90.0]
    candles = _candles(closes, [1000.0] * len(closes))

    signal = strategy.generate_signal("RELIANCE", candles)

    assert signal.signal_type == SignalType.SELL


def test_invalid_ema_window_ordering_rejected():
    with pytest.raises(ValueError, match="Fast EMA"):
        IntradayVwapMomentumStrategy(fast_ema=21, slow_ema=9)


def test_invalid_rsi_band_rejected():
    with pytest.raises(ValueError, match="RSI band"):
        IntradayVwapMomentumStrategy(rsi_min=80.0, rsi_max=50.0)


def test_warmup_period_is_max_of_windows_plus_two():
    strategy = _strategy(fast_ema=9, slow_ema=21, rsi_period=14, volume_avg_window=20)
    assert strategy.warmup_period == max(21, 14, 20) + 2


def test_session_vwap_resets_each_trading_day():
    """VWAP must never accumulate across days — a low-volume day-2 bar's
    VWAP should reflect only day 2's own bars, not be dragged toward day 1's
    price level."""
    day1 = _candles([100.0, 100.0, 100.0], [1000.0, 1000.0, 1000.0], day_offset=0)
    day2 = _candles([200.0], [1000.0], day_offset=1)
    candles = day1 + day2

    closes = pd.Series([c.close for c in candles])
    highs = pd.Series([c.high for c in candles])
    lows = pd.Series([c.low for c in candles])
    volumes = pd.Series([c.volume for c in candles], dtype=float)

    vwap = IntradayVwapMomentumStrategy._session_vwap(candles, highs, lows, closes, volumes)

    # Day 2's single bar VWAP must equal day 2's own price (200), not a
    # blend with day 1's much lower prices (~100).
    assert vwap.iloc[-1] == pytest.approx(200.0)
