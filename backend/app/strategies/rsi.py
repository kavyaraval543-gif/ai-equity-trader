"""Relative Strength Index (RSI) strategy.

RSI is computed with a simple rolling-mean average of gains/losses (not
Wilder's exponential smoothing) — the simpler, more transparent variant,
consistent with keeping this strategy easy to reason about and test:

    gain[t]     = max(close[t] - close[t-1], 0)
    loss[t]     = max(close[t-1] - close[t], 0)
    avg_gain    = mean(gain, window=period)
    avg_loss    = mean(loss, window=period)
    RS          = avg_gain / avg_loss
    RSI         = 100 - 100 / (1 + RS)

If a window has zero average loss (pure up-move), RSI is 100. If a window
has zero average gain AND zero average loss (flat prices), RSI is defined
here as 50 (neutral) rather than left undefined.

Documented signal rule — entering the zone triggers the signal (not exiting
it, which is a different common convention):

    BUY  when RSI crosses FROM >= oversold_threshold TO < oversold_threshold
         on the current bar (RSI just dropped INTO the oversold region).
    SELL when RSI crosses FROM <= overbought_threshold TO > overbought_threshold
         on the current bar (RSI just rose INTO the overbought region).

This does not claim to be profitable or to guarantee any return.
"""
from datetime import datetime, timezone

import pandas as pd

from app.core.config import get_settings
from app.market_data.base import Candle
from app.models.enums import SignalType
from app.strategies.base import BaseStrategy, StrategySignal


class RsiStrategy(BaseStrategy):
    name = "RSI"

    def __init__(
        self,
        period: int | None = None,
        oversold: float | None = None,
        overbought: float | None = None,
    ) -> None:
        settings = get_settings()
        self.period = period if period is not None else settings.rsi_period
        self.oversold = oversold if oversold is not None else settings.rsi_oversold
        self.overbought = overbought if overbought is not None else settings.rsi_overbought

        if self.period < 1:
            raise ValueError("RSI period must be a positive integer.")
        if not (0 < self.oversold < self.overbought < 100):
            raise ValueError(
                f"RSI thresholds must satisfy 0 < oversold ({self.oversold}) < "
                f"overbought ({self.overbought}) < 100."
            )

    @property
    def warmup_period(self) -> int:
        # One extra bar so both the current and previous RSI can be computed.
        return self.period + 2

    def get_params(self) -> dict:
        return {"period": self.period, "oversold": self.oversold, "overbought": self.overbought}

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
                reason=(
                    f"Insufficient history: {len(candles)} bars available, "
                    f"{min_required} required for RSI({self.period})."
                ),
                indicator_data={"bars_available": len(candles), "bars_required": min_required},
                market_price=last_price,
                timestamp=now,
            )

        closes = pd.Series([c.close for c in candles])
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=self.period).mean()
        avg_loss = loss.rolling(window=self.period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(50.0)  # flat window (0 gain, 0 loss) -> neutral

        curr_rsi, prev_rsi = float(rsi.iloc[-1]), float(rsi.iloc[-2])
        last_price = candles[-1].close

        indicator_data = {
            "rsi_period": self.period,
            "oversold": self.oversold,
            "overbought": self.overbought,
            "rsi": round(curr_rsi, 2),
            "prev_rsi": round(prev_rsi, 2),
        }

        crossed_into_oversold = prev_rsi >= self.oversold and curr_rsi < self.oversold
        crossed_into_overbought = prev_rsi <= self.overbought and curr_rsi > self.overbought

        # Confidence scales with how deep into the zone the crossing landed.
        if crossed_into_oversold:
            depth = min(1.0, (self.oversold - curr_rsi) / self.oversold) if self.oversold else 0.0
            confidence = round(min(0.95, 0.5 + depth * 0.45), 2)
            return StrategySignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"RSI({self.period}) crossed below {self.oversold} (oversold): {prev_rsi:.1f} -> {curr_rsi:.1f}.",
                indicator_data=indicator_data,
                market_price=last_price,
                timestamp=now,
            )
        if crossed_into_overbought:
            depth = min(1.0, (curr_rsi - self.overbought) / (100 - self.overbought)) if self.overbought < 100 else 0.0
            confidence = round(min(0.95, 0.5 + depth * 0.45), 2)
            return StrategySignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"RSI({self.period}) crossed above {self.overbought} (overbought): {prev_rsi:.1f} -> {curr_rsi:.1f}.",
                indicator_data=indicator_data,
                market_price=last_price,
                timestamp=now,
            )

        return StrategySignal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            confidence=0.5,
            strategy_name=self.name,
            reason=f"RSI({self.period}) at {curr_rsi:.1f} — no zone crossing on the latest bar.",
            indicator_data=indicator_data,
            market_price=last_price,
            timestamp=now,
        )
