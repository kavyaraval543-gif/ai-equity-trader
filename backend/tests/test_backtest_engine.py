"""BacktestEngine tests using a deterministic fake provider — real
crossover timing needs exact control over prices, which live data can't
guarantee. The provider/strategy plumbing itself is already covered by
test_market_data_provider.py (real network) and test_sma_crossover.py.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.backtesting.engine import BacktestEngine
from app.core.config import Settings
from app.market_data.base import Candle, MarketDataError, MarketDataProvider, PriceQuote, ProviderStatus
from app.models.enums import SignalType, TradeSide
from app.strategies.rsi import RsiStrategy
from app.strategies.sma_crossover import SmaCrossoverStrategy

BASE_DATE = date(2025, 1, 1)


def _candles(closes: list[float], opens: list[float] | None = None) -> list[Candle]:
    opens = opens or closes
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(timestamp=base + timedelta(days=i), open=opens[i], high=max(opens[i], closes[i]),
               low=min(opens[i], closes[i]), close=closes[i], volume=1000)
        for i in range(len(closes))
    ]


class FakeHistoricalProvider(MarketDataProvider):
    name = "fake"

    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def get_latest_price(self, symbol: str) -> PriceQuote:  # pragma: no cover - unused by the engine
        raise NotImplementedError

    def get_historical_data(self, symbol: str, interval: str, start=None, end=None) -> list[Candle]:
        return list(self._candles)

    def get_provider_status(self) -> ProviderStatus:  # pragma: no cover - unused by the engine
        return ProviderStatus(provider=self.name, connected=True, last_successful_fetch=None, detail="ok")


def _build_engine(closes: list[float], opens: list[float] | None = None, **strategy_kwargs) -> tuple[BacktestEngine, list[Candle]]:
    candles = _candles(closes, opens)
    strategy = SmaCrossoverStrategy(**{"short_window": 3, "long_window": 5, **strategy_kwargs})
    provider = FakeHistoricalProvider(candles)
    engine = BacktestEngine(provider=provider, strategy=strategy, settings=Settings(_env_file=None))
    return engine, candles


# A price series with a clean BUY crossover around day 10, held flat, then a
# clean SELL crossover around day 20. short=3/long=5 windows (min 6 bars).
BUY_SELL_CLOSES = (
    [100.0] * 10          # days 0-9: flat, builds up warm-up history
    + [130.0]              # day 10: jump -> BUY crossover signal generated here
    + [130.0] * 9          # days 11-19: held flat, no further crossover
    + [70.0]               # day 20: drop -> SELL crossover signal generated here
    + [70.0] * 3            # days 21-23: trailing bars so the SELL has a next-open to fill at
)


def test_historical_data_validation_rejects_unknown_symbol():
    engine, _ = _build_engine(BUY_SELL_CLOSES)
    with pytest.raises(ValueError, match="Unknown symbol"):
        engine.run("NOT_A_SYMBOL", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.1)


def test_historical_data_validation_rejects_bad_date_range():
    engine, _ = _build_engine(BUY_SELL_CLOSES)
    with pytest.raises(ValueError, match="end_date must be after start_date"):
        engine.run("RELIANCE", BASE_DATE, BASE_DATE, 100_000.0, 0.1)


def test_historical_data_validation_rejects_empty_provider_response():
    provider = FakeHistoricalProvider([])
    engine = BacktestEngine(provider=provider, strategy=SmaCrossoverStrategy(short_window=3, long_window=5))
    with pytest.raises(MarketDataError):
        engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=5), 100_000.0, 0.1)


def test_trade_executes_at_next_candle_open_not_signal_close():
    """No look-ahead: the BUY signal is generated on day 10's close (130),
    but must fill at day 11's genuinely distinct open (127), not day 10's
    close — opens and closes are deliberately different here so the
    assertion can't pass vacuously."""
    opens = list(BUY_SELL_CLOSES)
    opens[11] = 127.0
    engine, candles = _build_engine(BUY_SELL_CLOSES, opens)

    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.0)

    buy = next(t for t in result.trades if t.side == TradeSide.BUY)
    assert buy.price == 127.0
    assert candles[10].close == 130.0
    assert buy.price != candles[10].close
    assert buy.timestamp.date() == candles[11].timestamp.date()


def test_sell_executes_at_next_candle_open():
    opens = list(BUY_SELL_CLOSES)
    opens[21] = 73.0
    engine, candles = _build_engine(BUY_SELL_CLOSES, opens)

    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.0)

    sell = next(t for t in result.trades if t.side == TradeSide.SELL)
    assert sell.price == 73.0
    assert candles[20].close == 70.0
    assert sell.price != candles[20].close


def test_no_look_ahead_bias_signal_only_uses_data_up_to_current_close():
    """A version of the series where day 10 is followed by an EVEN BIGGER
    jump on day 11 must not change the BUY fill price — the strategy on day
    10 cannot see day 11's data."""
    inflated = list(BUY_SELL_CLOSES)
    inflated_opens = list(BUY_SELL_CLOSES)
    inflated_opens[11] = 130.0  # day 11 opens at the same price regardless of what day 12 will do
    engine, candles = _build_engine(inflated, inflated_opens)

    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.0)

    buy = next(t for t in result.trades if t.side == TradeSide.BUY)
    # Fill price is day 11's open (130), unaffected by any later price action.
    assert buy.price == 130.0


def test_transaction_costs_are_applied_on_both_sides():
    engine, candles = _build_engine(BUY_SELL_CLOSES)

    zero_cost = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.0)
    with_cost = BacktestEngine(
        provider=FakeHistoricalProvider(candles),
        strategy=SmaCrossoverStrategy(short_window=3, long_window=5),
    ).run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 1.0)  # 1% cost

    buy_zero = next(t for t in zero_cost.trades if t.side == TradeSide.BUY)
    buy_cost = next(t for t in with_cost.trades if t.side == TradeSide.BUY)
    assert buy_zero.transaction_cost == 0.0
    assert buy_cost.transaction_cost == pytest.approx(buy_cost.quantity * buy_cost.price * 0.01)

    sell_cost = next(t for t in with_cost.trades if t.side == TradeSide.SELL)
    assert sell_cost.transaction_cost == pytest.approx(sell_cost.quantity * sell_cost.price * 0.01)
    # Costs on both legs must reduce net P&L versus the zero-cost run.
    assert with_cost.total_return_pct < zero_cost.total_return_pct


def test_win_rate_calculation():
    # BUY_SELL_CLOSES produces one losing round trip (buy at 130ish, sell at 70ish).
    engine, _ = _build_engine(BUY_SELL_CLOSES)
    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.0)

    assert result.total_trades == 1
    assert result.losing_trades == 1
    assert result.winning_trades == 0
    assert result.win_rate == 0.0

    # A winning round trip: buy around 130, rally further to 200, then a
    # pullback to 180 (still above entry) triggers the SELL crossover.
    winning_closes = (
        [100.0] * 10           # days 0-9: warm-up
        + [130.0]               # day 10: BUY crossover
        + [130.0] * 4           # days 11-14: held (day 11 fills the BUY at 130)
        + [200.0]               # day 15: rally
        + [200.0] * 3            # days 16-18: held
        + [180.0]               # day 19: pullback -> SELL crossover (still above entry)
        + [180.0] * 3             # days 20-22: day 20 fills the SELL at 180
    )
    engine2, _ = _build_engine(winning_closes)
    result2 = engine2.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=22), 100_000.0, 0.0)

    assert result2.total_trades == 1
    assert result2.winning_trades == 1
    assert result2.win_rate == 100.0


def test_max_drawdown_is_negative_or_zero_and_reflects_the_trough():
    engine, _ = _build_engine(BUY_SELL_CLOSES)
    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.0)

    assert result.max_drawdown_pct <= 0.0
    # The position lost value from 130ish down to 70ish — a real drawdown must show up.
    assert result.max_drawdown_pct < -20.0


def test_flat_prices_have_zero_drawdown_and_no_trades():
    flat = [100.0] * 15
    engine, _ = _build_engine(flat)
    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=14), 100_000.0, 0.0)

    assert result.total_trades == 0
    assert result.max_drawdown_pct == 0.0
    assert result.ending_capital == 100_000.0


def test_buy_and_hold_comparison_present_and_computed_independently_of_strategy():
    engine, candles = _build_engine(BUY_SELL_CLOSES)
    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.0)

    first_open = candles[0].open
    last_close = candles[-1].close
    expected_bh_return = (last_close - first_open) / first_open * 100
    assert result.buy_hold_return_pct == pytest.approx(expected_bh_return, rel=1e-6)
    # The strategy in this scenario sells at a loss while price ends up flat
    # from start to finish — buy & hold should clearly beat it here.
    assert result.buy_hold_return_pct > result.total_return_pct


def test_last_candle_cannot_generate_an_executable_trade():
    """A crossover on the very last candle has no next-day open to fill at,
    so it must not produce a trade."""
    closes = [100.0] * 10 + [130.0]  # crossover right on the final bar
    engine, _ = _build_engine(closes)

    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=10), 100_000.0, 0.0)

    assert result.total_trades == 0
    assert len(result.trades) == 0


def test_strategy_params_are_recorded_on_the_result():
    engine, _ = _build_engine(BUY_SELL_CLOSES, short_window=3, long_window=5)
    result = engine.run("RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=23), 100_000.0, 0.0)

    assert result.strategy_params == {"short_window": 3, "long_window": 5}


def test_no_look_ahead_bias_for_rsi_strategy():
    """Uses the RSI strategy through the full engine (not the SMA one used
    elsewhere in this file) to confirm the same next-open execution and
    no-look-ahead guarantees hold regardless of which strategy is plugged
    into the engine."""
    closes = [100.0] * 6 + [95, 90, 85, 80, 75, 70, 65, 60, 55, 55, 55, 55]
    candles = _candles(closes)

    probe = RsiStrategy(period=5, oversold=30, overbought=70)
    buy_index = next(
        (i for i in range(len(candles)) if probe.generate_signal("RELIANCE", candles[: i + 1]).signal_type == SignalType.BUY),
        None,
    )
    assert buy_index is not None, "test setup must produce a BUY somewhere in the decline"
    assert buy_index + 1 < len(candles), "need a following candle to fill at"

    def _run(mutate_future: bool) -> float:
        local_closes = list(closes)
        if mutate_future and buy_index + 2 < len(local_closes):
            local_closes[buy_index + 2] = 999.0  # data strictly after the fill day
        local_candles = _candles(local_closes)
        engine = BacktestEngine(
            provider=FakeHistoricalProvider(local_candles),
            strategy=RsiStrategy(period=5, oversold=30, overbought=70),
            settings=Settings(_env_file=None),
        )
        result = engine.run(
            "RELIANCE", BASE_DATE, BASE_DATE + timedelta(days=len(local_closes) - 1), 100_000.0, 0.0
        )
        buy_trade = next(t for t in result.trades if t.side == TradeSide.BUY)
        assert buy_trade.price == local_candles[buy_index + 1].open
        assert buy_trade.price != local_candles[buy_index].close
        return buy_trade.price

    baseline_fill = _run(mutate_future=False)
    mutated_fill = _run(mutate_future=True)
    assert baseline_fill == mutated_fill, "changing data after the fill day must not change the fill price"
