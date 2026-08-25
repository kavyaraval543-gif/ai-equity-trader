"""Intraday backtesting engine.

Completely isolated from the live trading system (like the daily
BacktestEngine): reads real intraday OHLCV from the existing market-data
provider and simulates in memory only. The caller persists results.

Execution assumption (identical convention to the daily engine, extended
with slippage): a signal is generated from a candle's CLOSE; if actionable,
it is filled at the NEXT candle's OPEN, with slippage applied against the
trader (worse than the raw open) and then transaction cost on top of that.
Exit conditions (stop-loss, target, trailing stop, max holding time,
session-end, strategy exit) are evaluated the same way — checked against
each candle's CLOSE, executed at the next candle's OPEN — so entries and
exits share one uniform, auditable timing rule.

    Signal/exit condition true at candle[i].close
            |
            v
    Executed at candle[i+1].open
            |
            v
    price *= (1 +/- slippage_percent/100)   [worse for the trader]
            |
            v
    transaction_cost = qty * price * transaction_cost_percent/100

VWAP (used by the strategy) is recomputed fresh each trading day; this
engine does not need to know that — it only affects what the strategy
returns, never the engine's own bar-by-bar bookkeeping.

Data-provider limitation (see app/market_data/yahoo_provider.py and the
Settings.intraday_max_lookback_days default of 60): Yahoo Finance rejects
5m/15m history requests older than 60 days with "The requested range must
be within the last 60 days." This engine validates the requested
`start_date` against that limit up front and raises a clear error rather
than silently returning a shorter/different range.

Daily-scoped counters (trades today, realized P&L today) reset at each
trading-day boundary found in the data. `consecutive_losses` and the
cooldown timer are NOT reset daily — they track continuously across the
whole backtest, matching how the live IntradayRiskEngine's in-memory state
works (see app/scheduler/intraday_scheduler.py).
"""
import math
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core.config import Settings, get_settings
from app.market_data.base import Candle, MarketDataError, MarketDataProvider
from app.market_data.factory import get_market_data_provider
from app.market_data.symbols import DEFAULT_SYMBOLS
from app.models.enums import ExitReason, SignalType, TradeSide
from app.risk import intraday_rules
from app.strategies.base import BaseStrategy
from app.strategies.intraday_vwap_momentum import IntradayVwapMomentumStrategy

from app.backtesting.intraday_results import IntradayBacktestResult, IntradayBacktestTradeResult

INTRADAY_INTERVALS = ("5m", "15m")
# Small fixed calendar-day buffer before start_date so the strategy's
# indicators (a couple dozen bars) are warmed up on day one of the
# requested range — unlike the daily engine, intraday bars are dense enough
# that a few extra calendar days is always plenty, regardless of strategy
# parameters.
_WARMUP_BUFFER_CALENDAR_DAYS = 5


class IntradayBacktestEngine:
    def __init__(
        self,
        provider: MarketDataProvider | None = None,
        strategy: BaseStrategy | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or get_market_data_provider()
        self.strategy = strategy or IntradayVwapMomentumStrategy()
        self.tz = ZoneInfo(self.settings.market_timezone)

    def run(
        self,
        symbol: str,
        interval: str,
        start_date: date,
        end_date: date,
        starting_capital: float,
        transaction_cost_percent: float,
        slippage_percent: float,
    ) -> IntradayBacktestResult:
        symbol = symbol.upper()
        if symbol not in DEFAULT_SYMBOLS:
            raise ValueError(f"Unknown symbol '{symbol}'. Configured symbols: {DEFAULT_SYMBOLS}")
        if interval not in INTRADAY_INTERVALS:
            raise ValueError(f"Unsupported intraday interval '{interval}'. Supported: {INTRADAY_INTERVALS}")
        if end_date <= start_date:
            raise ValueError("end_date must be after start_date")
        if starting_capital <= 0:
            raise ValueError("starting_capital must be positive")

        days_ago = (datetime.now(self.tz).date() - start_date).days
        if days_ago > self.settings.intraday_max_lookback_days:
            raise ValueError(
                f"start_date {start_date} is {days_ago} days ago. The market data provider only supports "
                f"{interval} history within the last {self.settings.intraday_max_lookback_days} days "
                "(Yahoo Finance limitation) — choose a more recent start_date."
            )

        fetch_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc) - timedelta(
            days=_WARMUP_BUFFER_CALENDAR_DAYS
        )
        fetch_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)
        candles = self.provider.get_historical_data(symbol, interval=interval, start=fetch_start, end=fetch_end)
        if not candles:
            raise MarketDataError(f"No intraday data available for {symbol} in the requested range.")

        in_scope = [c for c in candles if start_date <= c.timestamp.astimezone(self.tz).date() <= end_date]
        if not in_scope:
            raise MarketDataError(f"No intraday trading data for {symbol} between {start_date} and {end_date}.")

        return self._simulate(symbol, interval, candles, start_date, end_date, starting_capital, transaction_cost_percent, slippage_percent)

    def _simulate(
        self,
        symbol: str,
        interval: str,
        candles: list[Candle],
        start_date: date,
        end_date: date,
        starting_capital: float,
        transaction_cost_percent: float,
        slippage_percent: float,
    ) -> IntradayBacktestResult:
        s = self.settings
        cash = starting_capital
        quantity = 0
        entry_price: float | None = None
        entry_time: datetime | None = None
        stop_loss_price: float | None = None
        target_price: float | None = None
        peak_price: float = 0.0

        trades: list[IntradayBacktestTradeResult] = []
        equity_curve: list[float] = []
        pending_signal: SignalType | None = None
        pending_exit_reason: ExitReason | None = None

        current_day: date | None = None
        trades_today = 0
        realized_pnl_today = 0.0
        consecutive_losses = 0
        last_loss_at: datetime | None = None
        trading_days: set[date] = set()

        def local_ts(c: Candle) -> datetime:
            return c.timestamp.astimezone(self.tz)

        for i, candle in enumerate(candles):
            ts = local_ts(candle)
            day = ts.date()
            in_scope = start_date <= day <= end_date

            if day != current_day:
                current_day = day
                trades_today = 0
                realized_pnl_today = 0.0

            is_last_bar_of_day = i + 1 >= len(candles) or local_ts(candles[i + 1]).date() != day

            # --- Step 1: execute any pending signal at THIS candle's open ---
            if pending_signal is not None:
                exec_price_raw = candle.open
                if pending_signal == SignalType.BUY and quantity == 0:
                    price = exec_price_raw * (1 + slippage_percent / 100)
                    slippage_cost = (price - exec_price_raw) * 1  # per-share, scaled by qty below
                    capital_for_trade = min(cash, s.intraday_risk_max_capital_per_trade_pct * starting_capital)
                    cost_multiplier = 1 + (transaction_cost_percent / 100)
                    qty = math.floor(capital_for_trade / (price * cost_multiplier))
                    if qty >= 1:
                        cost = qty * price * (transaction_cost_percent / 100)
                        cash -= qty * price + cost
                        quantity = qty
                        entry_price = price
                        entry_time = ts
                        peak_price = price
                        stop_loss_price = price * (1 - s.intraday_stop_loss_percent / 100) if s.intraday_stop_loss_percent else None
                        target_price = price * (1 + s.intraday_target_percent / 100) if s.intraday_target_percent else None
                        trades_today += 1
                        trades.append(
                            IntradayBacktestTradeResult(
                                side=TradeSide.BUY, quantity=qty, price=price, transaction_cost=cost,
                                slippage_cost=slippage_cost * qty, realized_pnl=None, exit_reason=None,
                                timestamp=candle.timestamp,
                            )
                        )
                elif pending_signal == SignalType.SELL and quantity > 0:
                    price = exec_price_raw * (1 - slippage_percent / 100)
                    slippage_cost = (exec_price_raw - price) * quantity
                    cost = quantity * price * (transaction_cost_percent / 100)
                    proceeds = quantity * price - cost
                    pnl = (price - entry_price) * quantity - cost
                    cash += proceeds
                    realized_pnl_today += pnl
                    trades_today += 1
                    if pnl < 0:
                        consecutive_losses += 1
                        last_loss_at = ts
                    else:
                        consecutive_losses = 0
                    trades.append(
                        IntradayBacktestTradeResult(
                            side=TradeSide.SELL, quantity=quantity, price=price, transaction_cost=cost,
                            slippage_cost=slippage_cost, realized_pnl=pnl, exit_reason=pending_exit_reason,
                            timestamp=candle.timestamp,
                        )
                    )
                    quantity = 0
                    entry_price = None
                    entry_time = None
                pending_signal = None
                pending_exit_reason = None

            if not in_scope:
                continue

            trading_days.add(day)
            equity_curve.append(cash + (quantity * candle.close if quantity > 0 else 0.0))

            if i + 1 >= len(candles):
                continue  # no next bar to fill at — never generate a new signal here

            # --- Step 2: if holding, check exit rules against this candle's close ---
            if quantity > 0:
                exit_reason = self._check_exit_rules(
                    candle.close, stop_loss_price, target_price, peak_price, entry_time, ts, is_last_bar_of_day
                )
                peak_price = max(peak_price, candle.close)
                if exit_reason is not None:
                    pending_signal = SignalType.SELL
                    pending_exit_reason = exit_reason
                    continue  # exit takes priority over asking the strategy this bar

                strategy_signal = self.strategy.generate_signal(symbol, candles[: i + 1])
                if strategy_signal.signal_type == SignalType.SELL:
                    pending_signal = SignalType.SELL
                    pending_exit_reason = ExitReason.STRATEGY_EXIT
                continue

            # --- Step 3: flat — consider a new entry, gated by intraday risk rules ---
            if intraday_rules.is_max_trades_per_day_reached(trades_today, s.intraday_risk_max_trades_per_day):
                continue
            if intraday_rules.is_daily_loss_limit_reached(realized_pnl_today, starting_capital, s.intraday_risk_max_daily_loss_pct):
                continue
            if intraday_rules.is_max_consecutive_losses_reached(consecutive_losses, s.intraday_risk_max_consecutive_losses):
                continue
            if intraday_rules.is_in_cooldown(ts, last_loss_at, s.intraday_risk_cooldown_minutes):
                continue
            if intraday_rules.is_near_session_end(ts, s.market_session_end, s.intraday_no_entry_minutes_before_close):
                continue

            strategy_signal = self.strategy.generate_signal(symbol, candles[: i + 1])
            if strategy_signal.signal_type == SignalType.BUY:
                pending_signal = SignalType.BUY

        return self._build_result(
            symbol, interval, starting_capital, cash, quantity, entry_price, candles, trades, equity_curve,
            trading_days, transaction_cost_percent, slippage_percent,
        )

    def _check_exit_rules(
        self,
        close: float,
        stop_loss_price: float | None,
        target_price: float | None,
        peak_price: float,
        entry_time: datetime | None,
        now: datetime,
        is_last_bar_of_day: bool,
    ) -> ExitReason | None:
        if stop_loss_price is not None and close <= stop_loss_price:
            return ExitReason.STOP_LOSS
        if target_price is not None and close >= target_price:
            return ExitReason.TARGET_REACHED
        if self.settings.intraday_trailing_stop_enabled:
            trailing_stop_price = peak_price * (1 - self.settings.intraday_trailing_stop_percent / 100)
            if close <= trailing_stop_price:
                return ExitReason.TRAILING_STOP
        if entry_time is not None and intraday_rules.has_exceeded_max_holding_time(
            entry_time, now, self.settings.intraday_max_holding_minutes
        ):
            return ExitReason.MAX_HOLDING_TIME
        if self.settings.intraday_force_close_at_session_end and is_last_bar_of_day:
            return ExitReason.SESSION_END
        return None

    def _build_result(
        self,
        symbol: str,
        interval: str,
        starting_capital: float,
        cash: float,
        open_quantity: int,
        open_entry_price: float | None,
        candles: list[Candle],
        trades: list[IntradayBacktestTradeResult],
        equity_curve: list[float],
        trading_days: set[date],
        transaction_cost_percent: float,
        slippage_percent: float,
    ) -> IntradayBacktestResult:
        ending_capital = equity_curve[-1] if equity_curve else cash
        total_pnl = ending_capital - starting_capital
        total_return_pct = (total_pnl / starting_capital) * 100

        sells = [t for t in trades if t.side == TradeSide.SELL]
        total_trades = len(sells)
        wins = [t.realized_pnl for t in sells if (t.realized_pnl or 0) > 0]
        losses = [t.realized_pnl for t in sells if (t.realized_pnl or 0) <= 0]
        winning_trades = len(wins)
        losing_trades = len(losses)
        win_rate = (winning_trades / total_trades * 100) if total_trades else 0.0
        avg_win = (sum(wins) / len(wins)) if wins else 0.0
        avg_loss = (sum(losses) / len(losses)) if losses else 0.0
        gross_profit = sum(wins)
        gross_loss = abs(sum(losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

        longest_losing_streak = 0
        current_streak = 0
        for t in sells:
            if (t.realized_pnl or 0) < 0:
                current_streak += 1
                longest_losing_streak = max(longest_losing_streak, current_streak)
            else:
                current_streak = 0

        max_drawdown_pct = self._max_drawdown(equity_curve)
        trading_day_count = len(trading_days) or 1
        trades_per_day = total_trades / trading_day_count

        return IntradayBacktestResult(
            symbol=symbol,
            interval=interval,
            strategy_name=self.strategy.name,
            strategy_params=self.strategy.get_params(),
            starting_capital=starting_capital,
            ending_capital=ending_capital,
            total_pnl=total_pnl,
            total_return_pct=total_return_pct,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown_pct,
            longest_losing_streak=longest_losing_streak,
            trading_days=len(trading_days),
            trades_per_day=trades_per_day,
            transaction_cost_percent=transaction_cost_percent,
            slippage_percent=slippage_percent,
            trades=trades,
        )

    @staticmethod
    def _max_drawdown(equity_curve: list[float]) -> float:
        if not equity_curve:
            return 0.0
        peak = equity_curve[0]
        max_dd = 0.0
        for value in equity_curve:
            peak = max(peak, value)
            if peak > 0:
                dd = (value - peak) / peak * 100
                max_dd = min(max_dd, dd)
        return max_dd
