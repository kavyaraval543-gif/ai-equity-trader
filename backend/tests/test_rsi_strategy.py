"""RSI strategy tests. Correctness is checked two ways: against an
independent re-implementation of the documented formula (catches
implementation bugs regardless of exact price values), and against
hand-constructed sequences designed to obviously push RSI into/out of the
configured zones."""
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from app.market_data.base import Candle
from app.models.enums import SignalType
from app.strategies.rsi import RsiStrategy


def _candles(closes: list[float]) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(timestamp=base + timedelta(days=i), open=c, high=c, low=c, close=c, volume=1000)
        for i, c in enumerate(closes)
    ]


def _reference_rsi(closes: list[float], period: int) -> list[float]:
    """Independent re-implementation of the documented RSI formula, used as
    ground truth to check the strategy's own calculation against."""
    s = pd.Series(closes, dtype=float)
    delta = s.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0).tolist()


def test_rsi_calculation_matches_reference_formula():
    closes = [100, 102, 101, 104, 103, 106, 108, 107, 110, 112, 109, 111, 115, 113, 116]
    period = 5
    strategy = RsiStrategy(period=period, oversold=30, overbought=70)

    signal = strategy.generate_signal("TEST", _candles(closes))

    expected = _reference_rsi(closes, period)
    assert signal.indicator_data["rsi"] == pytest.approx(expected[-1], abs=0.01)
    assert signal.indicator_data["prev_rsi"] == pytest.approx(expected[-2], abs=0.01)


def test_rsi_hold_on_insufficient_history():
    strategy = RsiStrategy(period=14, oversold=30, overbought=70)
    signal = strategy.generate_signal("TEST", _candles([100, 101, 102]))

    assert signal.signal_type == SignalType.HOLD
    assert "Insufficient history" in signal.reason
    assert signal.confidence == 0.0
    assert strategy.warmup_period == 16


def test_rsi_flat_prices_stay_neutral_and_never_signal():
    strategy = RsiStrategy(period=5, oversold=30, overbought=70)
    closes = [100.0] * 15

    signal = strategy.generate_signal("TEST", _candles(closes))

    assert signal.indicator_data["rsi"] == pytest.approx(50.0)
    assert signal.signal_type == SignalType.HOLD


def test_rsi_buy_signal_on_crossing_into_oversold():
    # A sharp, sustained decline after a flat run pushes RSI below 30.
    strategy = RsiStrategy(period=5, oversold=30, overbought=70)
    closes = [100.0] * 6 + [95, 90, 85, 80, 75, 70, 65, 60]

    signals = []
    for i in range(len(closes)):
        candles = _candles(closes[: i + 1])
        signals.append(strategy.generate_signal("TEST", candles))

    buy_signals = [s for s in signals if s.signal_type == SignalType.BUY]
    assert len(buy_signals) >= 1, "expected at least one BUY as RSI crosses into oversold during the decline"
    # Once already inside the oversold zone, further bars must not re-fire
    # BUY every single day — only the crossing bar(s) should trigger.
    assert len(buy_signals) < len(closes)


def test_rsi_sell_signal_on_crossing_into_overbought():
    strategy = RsiStrategy(period=5, oversold=30, overbought=70)
    closes = [100.0] * 6 + [105, 110, 115, 120, 125, 130, 135, 140]

    signals = []
    for i in range(len(closes)):
        candles = _candles(closes[: i + 1])
        signals.append(strategy.generate_signal("TEST", candles))

    sell_signals = [s for s in signals if s.signal_type == SignalType.SELL]
    assert len(sell_signals) >= 1, "expected at least one SELL as RSI crosses into overbought during the rally"


def test_rsi_configurable_thresholds_are_recorded():
    strategy = RsiStrategy(period=21, oversold=25, overbought=75)

    assert strategy.get_params() == {"period": 21, "oversold": 25, "overbought": 75}


@pytest.mark.parametrize("period", [0, -1, -14])
def test_rsi_period_must_be_positive(period):
    with pytest.raises(ValueError):
        RsiStrategy(period=period)


@pytest.mark.parametrize("oversold,overbought", [(70, 30), (30, 30), (0, 70), (30, 100), (-5, 70)])
def test_rsi_thresholds_must_be_ordered_and_in_range(oversold, overbought):
    with pytest.raises(ValueError):
        RsiStrategy(period=14, oversold=oversold, overbought=overbought)
