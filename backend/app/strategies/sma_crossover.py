"""Simple moving-average crossover strategy.

A short-window SMA crossing above a long-window SMA is treated as a BUY
signal; crossing below is treated as a SELL signal. No crossover on the
most recent bar produces HOLD. This is a plain, transparent technical rule
— it does not claim to be profitable or to guarantee any return.
"""
from datetime import datetime, timezone

import pandas as pd

from app.core.config import get_settings
from app.market_data.base import Candle
from app.models.enums import SignalType
from app.strategies.base import BaseStrategy, StrategySignal


class SmaCrossoverStrategy(BaseStrategy):
    name = "SMA_CROSSOVER"

    def __init__(self, short_window: int | None = None, long_window: int | None = None) -> None:
        settings = get_settings()
        self.short_window = short_window if short_window is not None else settings.sma_short_window
        self.long_window = long_window if long_window is not None else settings.sma_long_window

        if self.short_window < 1 or self.long_window < 1:
            raise ValueError("SMA windows must be positive integers.")
        if self.short_window >= self.long_window:
            raise ValueError(
                f"SMA fast period ({self.short_window}) must be less than the slow period ({self.long_window})."
            )

    @property
    def warmup_period(self) -> int:
        return self.long_window

    def get_params(self) -> dict:
        return {"short_window": self.short_window, "long_window": self.long_window}

    def generate_signal(self, symbol: str, candles: list[Candle]) -> StrategySignal:
        now = datetime.now(timezone.utc)
        min_required = self.long_window + 1

        if len(candles) < min_required:
            last_price = candles[-1].close if candles else 0.0
            return StrategySignal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                confidence=0.0,
                strategy_name=self.name,
                reason=(
                    f"Insufficient history: {len(candles)} bars available, "
                    f"{min_required} required for SMA({self.short_window})/SMA({self.long_window})."
                ),
                indicator_data={"bars_available": len(candles), "bars_required": min_required},
                market_price=last_price,
                timestamp=now,
            )

        closes = pd.Series([c.close for c in candles])
        sma_short = closes.rolling(window=self.short_window).mean()
        sma_long = closes.rolling(window=self.long_window).mean()

        curr_short, curr_long = sma_short.iloc[-1], sma_long.iloc[-1]
        prev_short, prev_long = sma_short.iloc[-2], sma_long.iloc[-2]
        last_price = candles[-1].close

        indicator_data = {
            "sma_short_window": self.short_window,
            "sma_long_window": self.long_window,
            "sma_short": round(float(curr_short), 4),
            "sma_long": round(float(curr_long), 4),
            "prev_sma_short": round(float(prev_short), 4),
            "prev_sma_long": round(float(prev_long), 4),
        }

        crossed_up = prev_short <= prev_long and curr_short > curr_long
        crossed_down = prev_short >= prev_long and curr_short < curr_long

        # Confidence scales with how far the short MA has moved from the long
        # MA relative to price — a larger separation reads as a stronger signal.
        separation = abs(curr_short - curr_long) / last_price if last_price else 0.0
        confidence = round(min(0.95, 0.5 + separation * 20), 2)

        if crossed_up:
            return StrategySignal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                confidence=confidence,
                strategy_name=self.name,
                reason=(
                    f"Short SMA({self.short_window}) crossed above long SMA({self.long_window})."
                ),
                indicator_data=indicator_data,
                market_price=last_price,
                timestamp=now,
            )
        if crossed_down:
            return StrategySignal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                confidence=confidence,
                strategy_name=self.name,
                reason=(
                    f"Short SMA({self.short_window}) crossed below long SMA({self.long_window})."
                ),
                indicator_data=indicator_data,
                market_price=last_price,
                timestamp=now,
            )

        return StrategySignal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            confidence=round(1 - min(0.5, separation * 20), 2),
            strategy_name=self.name,
            reason="No moving-average crossover on the latest bar.",
            indicator_data=indicator_data,
            market_price=last_price,
            timestamp=now,
        )
