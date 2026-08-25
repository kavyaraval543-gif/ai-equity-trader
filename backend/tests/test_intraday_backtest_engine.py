"""IntradayBacktestEngine tests using a deterministic scripted fake strategy
— exact control over WHEN a signal fires is needed to pin down fill timing,
exit-rule triggering, slippage/cost math, and risk-rule gating, none of
which real market data can guarantee bar-for-bar.

Every test disables whichever exit/risk knobs it isn't exercising (via a
`_settings` override), so each scenario isolates a single mechanism.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.backtesting.intraday_engine import IntradayBacktestEngine
from app.core.config import Settings
from app.market_data.base import Candle, MarketDataProvider, PriceQuote, ProviderStatus
from app.models.enums import ExitReason, SignalType, TradeSide
from app.strategies.base import BaseStrategy, StrategySignal

IST = ZoneInfo("Asia/Kolkata")


def _today() -> date:
    return datetime.now(IST).date()


class FakeIntradayProvider(MarketDataProvider):
    name = "fake"

    def __init__(self, candles: list[Candle]) -> None:
        self._candles = candles

    def get_latest_price(self, symbol: str) -> PriceQuote:  # pragma: no cover - unused
        raise NotImplementedError

    def get_historical_data(self, symbol: str, interval: str, start=None, end=None) -> list[Candle]:
        return list(self._candles)

    def get_provider_status(self) -> ProviderStatus:  # pragma: no cover - unused
        return ProviderStatus(provider=self.name, connected=True, last_successful_fetch=None, detail="ok")


class ScriptedStrategy(BaseStrategy):
    """Emits a fixed signal_type when the candle history reaches a given
    length, HOLD otherwise — gives full, index-precise control over
    entry/exit timing so exit-rule and risk-gating logic can be isolated
    from the real strategy's indicator math."""

    name = "SCRIPTED_FAKE"

    def __init__(self, script: dict[int, SignalType]) -> None:
        self._script = script

    @property
    def warmup_period(self) -> int:
        return 0

    def generate_signal(self, symbol: str, candles: list[Candle]) -> StrategySignal:
        n = len(candles)
        signal_type = self._script.get(n, SignalType.HOLD)
        return StrategySignal(
            symbol=symbol, signal_type=signal_type, confidence=0.9, strategy_name=self.name,
            reason="scripted", indicator_data={}, market_price=candles[-1].close, timestamp=candles[-1].timestamp,
        )


def _candles(
    closes: list[float], opens: list[float] | None = None, day: date | None = None, start_hour: int = 9,
    start_minute: int = 20, interval_minutes: int = 5, volume: float = 1000.0,
) -> list[Candle]:
    """Builds same-day 5-minute-spaced candles by default. Pass a list of
    (day_offset, close) style overrides via `opens` when a multi-day
    scenario is needed (see the SESSION_END test)."""
    day = day or _today()
    opens = opens or closes
    base = datetime(day.year, day.month, day.day, start_hour, start_minute, tzinfo=IST)
    out = []
    for i in range(len(closes)):
        ts = base + timedelta(minutes=interval_minutes * i)
        o, c = opens[i], closes[i]
        out.append(Candle(timestamp=ts, open=o, high=max(o, c), low=min(o, c), close=c, volume=volume))
    return out


def _settings(**overrides) -> Settings:
    """All exit/risk knobs disabled by default; each test re-enables only
    the one mechanism it is testing."""
    defaults = dict(
        intraday_stop_loss_percent=0.0,
        intraday_target_percent=0.0,
        intraday_trailing_stop_enabled=False,
        intraday_max_holding_minutes=0,
        intraday_force_close_at_session_end=False,
        intraday_risk_max_capital_per_trade_pct=1.0,
        intraday_risk_max_trades_per_day=1000,
        intraday_risk_max_daily_loss_pct=1.0,
        intraday_risk_max_consecutive_losses=1000,
        intraday_risk_cooldown_minutes=0,
        intraday_no_entry_minutes_before_close=0,
        intraday_max_lookback_days=60,
    )
    defaults.update(overrides)
    return Settings(_env_file=None, **defaults)


def _run(strategy, candles, settings=None, transaction_cost_percent=0.0, slippage_percent=0.0, starting_capital=100_000.0):
    engine = IntradayBacktestEngine(provider=FakeIntradayProvider(candles), strategy=strategy, settings=settings or _settings())
    day = candles[0].timestamp.astimezone(IST).date()
    # end_date must be strictly after start_date (engine validation) even
    # for single-day scenarios — one harmless extra phantom day beyond the
    # last real candle satisfies that without affecting the simulation
    # (nothing exists there in the fake provider's fixed candle list).
    end_day = candles[-1].timestamp.astimezone(IST).date() + timedelta(days=1)
    return engine.run("RELIANCE", "5m", day, end_day, starting_capital, transaction_cost_percent, slippage_percent)


# --- input validation ---


def test_rejects_unknown_symbol():
    engine = IntradayBacktestEngine(provider=FakeIntradayProvider([]), strategy=ScriptedStrategy({}), settings=_settings())
    with pytest.raises(ValueError, match="Unknown symbol"):
        engine.run("NOT_A_SYMBOL", "5m", _today(), _today(), 100_000.0, 0.0, 0.0)


def test_rejects_unsupported_interval():
    engine = IntradayBacktestEngine(provider=FakeIntradayProvider([]), strategy=ScriptedStrategy({}), settings=_settings())
    with pytest.raises(ValueError, match="Unsupported intraday interval"):
        engine.run("RELIANCE", "1h", _today(), _today(), 100_000.0, 0.0, 0.0)


def test_rejects_start_date_beyond_provider_lookback_limit():
    engine = IntradayBacktestEngine(provider=FakeIntradayProvider([]), strategy=ScriptedStrategy({}), settings=_settings())
    too_old = _today() - timedelta(days=90)
    with pytest.raises(ValueError, match="60 days"):
        engine.run("RELIANCE", "5m", too_old, _today(), 100_000.0, 0.0, 0.0)


# --- no-look-ahead / next-open fill ---


def test_buy_fills_at_next_candle_open_not_signal_bar_close():
    closes = [100.0] * 9
    opens = list(closes)
    opens[5] = 110.0  # distinct from candles[4].close(100) so the assertion can't pass vacuously
    candles = _candles(closes, opens)
    strategy = ScriptedStrategy({5: SignalType.BUY})  # signal generated when len(candles)==5, i.e. at loop i=4

    result = _run(strategy, candles)

    buy = result.trades[0]
    assert buy.side == TradeSide.BUY
    assert buy.price == 110.0
    assert candles[4].close == 100.0
    assert buy.timestamp == candles[5].timestamp


def test_signal_on_final_candle_produces_no_trade():
    """A signal on the very last candle has no next bar to fill at."""
    closes = [100.0] * 5
    candles = _candles(closes)
    strategy = ScriptedStrategy({5: SignalType.BUY})

    result = _run(strategy, candles)

    assert result.total_trades == 0
    assert len(result.trades) == 0


# --- slippage and transaction cost ---


def test_slippage_and_transaction_cost_applied_on_both_legs():
    closes = [100.0] * 9
    opens = list(closes)
    opens[5] = 110.0  # BUY fills here
    opens[8] = 90.0  # SELL fills here (a loss)
    candles = _candles(closes, opens)
    strategy = ScriptedStrategy({5: SignalType.BUY, 8: SignalType.SELL})

    result = _run(strategy, candles, transaction_cost_percent=0.5, slippage_percent=1.0)

    buy, sell = result.trades[0], result.trades[1]
    assert buy.side == TradeSide.BUY and sell.side == TradeSide.SELL

    # BUY: slippage makes the fill WORSE for the trader (higher).
    assert buy.price == pytest.approx(110.0 * 1.01)
    assert buy.slippage_cost == pytest.approx((buy.price - 110.0) * buy.quantity)
    assert buy.transaction_cost == pytest.approx(buy.quantity * buy.price * 0.005)

    # SELL: slippage makes the fill WORSE for the trader (lower).
    assert sell.price == pytest.approx(90.0 * 0.99)
    assert sell.slippage_cost == pytest.approx((90.0 - sell.price) * sell.quantity)
    assert sell.transaction_cost == pytest.approx(sell.quantity * sell.price * 0.005)
    assert sell.exit_reason == ExitReason.STRATEGY_EXIT

    expected_pnl = (sell.price - buy.price) * sell.quantity - sell.transaction_cost
    assert sell.realized_pnl == pytest.approx(expected_pnl)


def test_zero_slippage_and_cost_means_raw_open_price():
    closes = [100.0] * 6
    opens = list(closes)
    opens[5] = 123.45
    candles = _candles(closes, opens)
    strategy = ScriptedStrategy({5: SignalType.BUY})

    result = _run(strategy, candles, transaction_cost_percent=0.0, slippage_percent=0.0)

    buy = result.trades[0]
    assert buy.price == 123.45
    assert buy.slippage_cost == pytest.approx(0.0)
    assert buy.transaction_cost == pytest.approx(0.0)


# --- exit rules ---


def test_stop_loss_exit_fires_and_fills_at_next_open():
    closes = [100.0] * 9
    opens = list(closes)
    opens[5] = 100.0  # BUY fills at 100 -> stop-loss price = 98 (2%)
    closes[6] = 97.0  # breaches stop-loss on this candle's close
    opens[7] = 95.0  # exit fills here
    candles = _candles(closes, opens)
    strategy = ScriptedStrategy({5: SignalType.BUY})  # strategy itself never exits
    settings = _settings(intraday_stop_loss_percent=2.0)

    result = _run(strategy, candles, settings=settings)

    sell = result.trades[1]
    assert sell.exit_reason == ExitReason.STOP_LOSS
    assert sell.price == 95.0


def test_target_exit_fires_and_fills_at_next_open():
    closes = [100.0] * 9
    opens = list(closes)
    opens[5] = 100.0  # BUY fills at 100 -> target price = 102 (2%)
    closes[6] = 103.0  # reaches target on this candle's close
    opens[7] = 104.0
    candles = _candles(closes, opens)
    strategy = ScriptedStrategy({5: SignalType.BUY})
    settings = _settings(intraday_target_percent=2.0)

    result = _run(strategy, candles, settings=settings)

    sell = result.trades[1]
    assert sell.exit_reason == ExitReason.TARGET_REACHED
    assert sell.price == 104.0


def test_max_holding_time_exit():
    # 5-minute bars; BUY fills (and entry_time is stamped) at candle index 5.
    # max_holding_minutes=15 -> first candle at/after entry_time+15min is index 8.
    closes = [100.0] * 12
    opens = list(closes)
    opens[9] = 111.0  # exit fill
    candles = _candles(closes, opens)
    strategy = ScriptedStrategy({5: SignalType.BUY})
    settings = _settings(intraday_max_holding_minutes=15)

    result = _run(strategy, candles, settings=settings)

    sell = result.trades[1]
    assert sell.exit_reason == ExitReason.MAX_HOLDING_TIME
    assert sell.price == 111.0


def test_session_end_force_close_fills_at_next_days_open():
    """A force-close signaled on the last bar of a trading day fills at the
    NEXT trading day's opening bar — the engine's uniform signal-at-close/
    exec-at-next-open rule applies to exits too, including this one."""
    day1 = _today() - timedelta(days=1)
    day2 = _today()
    closes_day1 = [100.0] * 8
    opens_day1 = list(closes_day1)
    opens_day1[5] = 100.0  # BUY fills here, still well within day 1
    day1_candles = _candles(closes_day1, opens_day1, day=day1)

    day2_candles = _candles([100.0, 100.0], [120.0, 100.0], day=day2, start_hour=9, start_minute=20)
    candles = day1_candles + day2_candles

    strategy = ScriptedStrategy({5: SignalType.BUY})
    settings = _settings(intraday_force_close_at_session_end=True)

    result = _run(strategy, candles, settings=settings)

    sell = result.trades[1]
    assert sell.exit_reason == ExitReason.SESSION_END
    assert sell.timestamp.astimezone(IST).date() == day2
    assert sell.price == 120.0


# --- intraday-only risk gating, enforced inside the backtest engine itself ---


def test_max_trades_per_day_blocks_further_entries_same_day():
    closes = [100.0] * 14
    opens = list(closes)
    opens[5] = 100.0  # BUY fills
    opens[8] = 50.0  # SELL fills (a loss) -> trades_today reaches 2 here
    candles = _candles(closes, opens)
    # A second round trip is scripted (12 -> BUY) but must never fire once
    # the 2-trade daily cap is already reached by the first round trip.
    strategy = ScriptedStrategy({5: SignalType.BUY, 8: SignalType.SELL, 12: SignalType.BUY})
    settings = _settings(intraday_risk_max_trades_per_day=2)

    result = _run(strategy, candles, settings=settings)

    assert len(result.trades) == 2


def test_daily_loss_limit_blocks_further_entries_same_day():
    closes = [100.0] * 14
    opens = list(closes)
    opens[5] = 100.0
    opens[8] = 10.0  # a large loss when sold with full-capital sizing
    candles = _candles(closes, opens)
    strategy = ScriptedStrategy({5: SignalType.BUY, 8: SignalType.SELL, 12: SignalType.BUY})
    settings = _settings(intraday_risk_max_daily_loss_pct=0.01)  # 1% of 100,000 = 1,000

    result = _run(strategy, candles, settings=settings)

    assert result.trades[1].realized_pnl < -1000  # confirms the scenario really did breach the limit
    assert len(result.trades) == 2  # the scripted 3rd trade must not fire


def test_consecutive_losses_blocks_further_entries():
    closes = [100.0] * 14
    opens = list(closes)
    opens[5] = 100.0
    opens[8] = 90.0  # one losing round trip
    candles = _candles(closes, opens)
    strategy = ScriptedStrategy({5: SignalType.BUY, 8: SignalType.SELL, 12: SignalType.BUY})
    settings = _settings(intraday_risk_max_consecutive_losses=1, intraday_risk_max_daily_loss_pct=1.0)

    result = _run(strategy, candles, settings=settings)

    assert result.trades[1].realized_pnl < 0
    assert len(result.trades) == 2


def test_cooldown_blocks_immediate_reentry_but_allows_it_after_the_window():
    closes = [100.0] * 24
    opens = list(closes)
    opens[5] = 100.0
    opens[8] = 90.0  # losing round trip; the SELL fills at candle 8, so last_loss_at = candle 8's timestamp
    candles = _candles(closes, opens)
    # An immediate re-entry attempt on the very same bar as the loss (n=9
    # corresponds to loop index 8, the SELL-fill bar itself) must be
    # blocked by cooldown; a later one 20+ minutes later (n=20 -> index 19,
    # 55 minutes after the loss) must be allowed.
    strategy = ScriptedStrategy({5: SignalType.BUY, 8: SignalType.SELL, 9: SignalType.BUY, 20: SignalType.BUY})
    settings = _settings(intraday_risk_max_consecutive_losses=1000, intraday_risk_cooldown_minutes=20)

    result = _run(strategy, candles, settings=settings)

    # Only the losing round trip plus the later (post-cooldown) round trip
    # execute — the immediate re-entry at candle 9 must be skipped entirely.
    buys = [t for t in result.trades if t.side == TradeSide.BUY]
    assert len(buys) == 2
    assert buys[1].timestamp == candles[20].timestamp
