"""Intraday VWAP + trend + momentum strategy.

One transparent, rule-based intraday strategy — not a claim of
profitability, and no invented "AI confidence": every confidence value is a
deterministic function of which documented conditions were satisfied.

Indicators (all computed from the candle series only up to and including
the bar being evaluated — never future bars):

  - Trend: EMA(fast) vs EMA(slow) (defaults 9/21) on closing price.
  - Reference level: session VWAP (volume-weighted average price),
    recomputed from scratch each trading day using only that day's bars —
    typical_price = (high + low + close) / 3, VWAP = cumsum(typical_price *
    volume) / cumsum(volume). VWAP is a same-day, intraday-only measure; it
    is meaningless carried across days, so bars from earlier days in the
    warm-up window are excluded from today's VWAP calculation.
  - Momentum: RSI(period) (default 14), using the same simple rolling-mean
    formula as app/strategies/rsi.py.
  - Volume confirmation: current bar's volume vs. its own rolling average
    (default 20 bars) — skipped (never blocks a signal) if recent volume
    data looks unreliable (more than half of the last `volume_avg_window`
    bars have zero volume), which is documented via
    `indicator_data["volume_reliable"]` rather than silently substituted.

Entry rule (BUY) — all of the following on the same bar:
  1. Trend just turned bullish: EMA(fast) crosses above EMA(slow) this bar
     (prev fast <= prev slow, current fast > current slow). This is the
     trigger; the checks below are confirmations, not separate triggers —
     without a fresh crossover, the strategy holds even if 2-4 are true.
  2. Close is above today's session VWAP.
  3. RSI is within [rsi_min, rsi_max] (default 50-75) — has upward
     momentum, not already extremely overbought.
  4. Volume confirmation, when reliable: current volume > average volume *
     volume_multiplier.

Exit rule (SELL / strategy exit) — either of:
  a. Trend reverses: EMA(fast) crosses below EMA(slow) this bar.
  b. VWAP breakdown: close drops below VWAP this bar, having been above it
     the previous bar.

Confidence: starts at 0.5 and adds a fixed weight for each satisfied
confirming condition (trend 0.15, VWAP 0.15, RSI band 0.10, volume 0.10),
capped at 0.95 — never a free-floating or model-derived number.
"""
from datetime import datetime, timezone

import pandas as pd

from app.core.config import get_settings
from app.market_data.base import Candle
from app.models.enums import SignalType
from app.strategies.base import BaseStrategy, StrategySignal


class IntradayVwapMomentumStrategy(BaseStrategy):
    name = "INTRADAY_VWAP_MOMENTUM"

    def __init__(
        self,
        fast_ema: int | None = None,
        slow_ema: int | None = None,
        rsi_period: int | None = None,
        rsi_min: float | None = None,
        rsi_max: float | None = None,
        volume_avg_window: int | None = None,
        volume_multiplier: float | None = None,
    ) -> None:
        settings = get_settings()
        self.fast_ema = fast_ema if fast_ema is not None else settings.intraday_trend_fast_ema
        self.slow_ema = slow_ema if slow_ema is not None else settings.intraday_trend_slow_ema
        self.rsi_period = rsi_period if rsi_period is not None else settings.intraday_rsi_period
        self.rsi_min = rsi_min if rsi_min is not None else settings.intraday_rsi_min
        self.rsi_max = rsi_max if rsi_max is not None else settings.intraday_rsi_max
        self.volume_avg_window = volume_avg_window if volume_avg_window is not None else settings.intraday_volume_avg_window
        self.volume_multiplier = volume_multiplier if volume_multiplier is not None else settings.intraday_volume_multiplier

        if self.fast_ema < 1 or self.slow_ema < 1:
            raise ValueError("EMA windows must be positive integers.")
        if self.fast_ema >= self.slow_ema:
            raise ValueError(f"Fast EMA ({self.fast_ema}) must be less than slow EMA ({self.slow_ema}).")
        if self.rsi_period < 1:
            raise ValueError("RSI period must be a positive integer.")
        if not (0 < self.rsi_min < self.rsi_max < 100):
            raise ValueError(f"RSI band must satisfy 0 < rsi_min ({self.rsi_min}) < rsi_max ({self.rsi_max}) < 100.")
        if self.volume_avg_window < 1:
            raise ValueError("volume_avg_window must be a positive integer.")

    @property
    def warmup_period(self) -> int:
        return max(self.slow_ema, self.rsi_period, self.volume_avg_window) + 2

    def get_params(self) -> dict:
        return {
            "fast_ema": self.fast_ema,
            "slow_ema": self.slow_ema,
            "rsi_period": self.rsi_period,
            "rsi_min": self.rsi_min,
            "rsi_max": self.rsi_max,
            "volume_avg_window": self.volume_avg_window,
            "volume_multiplier": self.volume_multiplier,
        }

    def generate_signal(self, symbol: str, candles: list[Candle]) -> StrategySignal:
        now = datetime.now(timezone.utc)
        min_required = self.warmup_period

        if len(candles) < min_required:
            last_price = candles[-1].close if candles else 0.0
            return StrategySignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy_name=self.name,
                reason=f"Insufficient history: {len(candles)} bars available, {min_required} required.",
                indicator_data={"bars_available": len(candles), "bars_required": min_required},
                market_price=last_price,
                timestamp=now,
            )

        closes = pd.Series([c.close for c in candles])
        highs = pd.Series([c.high for c in candles])
        lows = pd.Series([c.low for c in candles])
        volumes = pd.Series([c.volume for c in candles], dtype=float)

        ema_fast = closes.ewm(span=self.fast_ema, adjust=False).mean()
        ema_slow = closes.ewm(span=self.slow_ema, adjust=False).mean()

        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=self.rsi_period).mean()
        avg_loss = loss.rolling(window=self.rsi_period).mean()
        rs = avg_gain / avg_loss
        rsi = (100 - (100 / (1 + rs))).fillna(50.0)

        vwap = self._session_vwap(candles, highs, lows, closes, volumes)

        avg_volume = volumes.rolling(window=self.volume_avg_window).mean()
        recent_volumes = volumes.iloc[-self.volume_avg_window:]
        volume_reliable = (recent_volumes == 0).sum() <= len(recent_volumes) / 2

        i = len(candles) - 1
        last_price = candles[-1].close

        curr_fast, prev_fast = ema_fast.iloc[i], ema_fast.iloc[i - 1]
        curr_slow, prev_slow = ema_slow.iloc[i], ema_slow.iloc[i - 1]
        curr_vwap, prev_vwap = vwap.iloc[i], vwap.iloc[i - 1]
        curr_rsi = rsi.iloc[i]
        curr_volume, curr_avg_volume = volumes.iloc[i], avg_volume.iloc[i]

        trend_crossed_up = prev_fast <= prev_slow and curr_fast > curr_slow
        trend_crossed_down = prev_fast >= prev_slow and curr_fast < curr_slow
        above_vwap = last_price > curr_vwap
        vwap_breakdown = last_price < curr_vwap and closes.iloc[i - 1] >= prev_vwap
        rsi_in_band = self.rsi_min <= curr_rsi <= self.rsi_max
        volume_confirmed = (not volume_reliable) or (curr_avg_volume > 0 and curr_volume > curr_avg_volume * self.volume_multiplier)

        indicator_data = {
            "ema_fast": round(float(curr_fast), 4),
            "ema_slow": round(float(curr_slow), 4),
            "vwap": round(float(curr_vwap), 4),
            "rsi": round(float(curr_rsi), 2),
            "volume": int(curr_volume),
            "avg_volume": round(float(curr_avg_volume), 2) if pd.notna(curr_avg_volume) else None,
            "volume_reliable": bool(volume_reliable),
            "above_vwap": bool(above_vwap),
            "rsi_in_band": bool(rsi_in_band),
            "volume_confirmed": bool(volume_confirmed),
        }

        def confidence_for(trend_ok: bool, vwap_ok: bool) -> float:
            score = 0.5
            score += 0.15 if trend_ok else 0.0
            score += 0.15 if vwap_ok else 0.0
            score += 0.10 if rsi_in_band else 0.0
            score += 0.10 if volume_confirmed else 0.0
            return round(min(0.95, score), 2)

        if trend_crossed_up and above_vwap and rsi_in_band and volume_confirmed:
            return StrategySignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=confidence_for(True, True),
                strategy_name=self.name,
                reason=(
                    f"EMA({self.fast_ema}) crossed above EMA({self.slow_ema}); price above session VWAP; "
                    f"RSI {curr_rsi:.1f} in [{self.rsi_min},{self.rsi_max}]"
                    + ("; volume confirmed" if volume_reliable else "; volume data unreliable, check skipped")
                    + "."
                ),
                indicator_data=indicator_data,
                market_price=last_price,
                timestamp=now,
            )

        if trend_crossed_down or vwap_breakdown:
            reason = (
                f"EMA({self.fast_ema}) crossed below EMA({self.slow_ema})."
                if trend_crossed_down
                else "Price broke below session VWAP."
            )
            return StrategySignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=confidence_for(trend_crossed_down, vwap_breakdown),
                strategy_name=self.name,
                reason=reason,
                indicator_data=indicator_data,
                market_price=last_price,
                timestamp=now,
            )

        return StrategySignal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            confidence=round(1 - confidence_for(trend_crossed_up, above_vwap) + 0.5, 2),
            strategy_name=self.name,
            reason="No fresh trend crossover confirmed by VWAP/RSI/volume on the latest bar.",
            indicator_data=indicator_data,
            market_price=last_price,
            timestamp=now,
        )

    @staticmethod
    def _session_vwap(candles: list[Candle], highs: pd.Series, lows: pd.Series, closes: pd.Series, volumes: pd.Series) -> pd.Series:
        """Volume-weighted average price, reset at the start of each trading
        day — never accumulated across days."""
        typical_price = (highs + lows + closes) / 3
        dates = pd.Series([c.timestamp.date() for c in candles])
        tp_vol = typical_price * volumes

        vwap = pd.Series(index=closes.index, dtype=float)
        for day in dates.unique():
            mask = dates == day
            cum_tp_vol = tp_vol[mask].cumsum()
            cum_vol = volumes[mask].cumsum()
            day_vwap = (cum_tp_vol / cum_vol).replace([float("inf"), float("-inf")], pd.NA)
            day_vwap = day_vwap.fillna(closes[mask])
            vwap.loc[mask] = day_vwap
        return vwap
