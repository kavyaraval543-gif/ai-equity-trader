"""Historical backtesting engine.

Completely isolated from the live autonomous-trading system: it never
imports or touches Portfolio, Position, Trade, or AutonomousState. It only
reads real historical OHLCV data from the existing market-data provider and
runs the existing SMA(10/30) strategy in memory. The caller (the API layer)
is responsible for persisting the result into the separate
BacktestRun/BacktestTrade tables.

Execution assumption (to avoid look-ahead bias): on each candle, the
strategy sees only that candle's close and everything before it. If that
produces an actionable BUY/SELL signal, the trade is simulated at the
*next* candle's open — never at the same candle's close, which the
strategy could not have traded at in real time. The very last candle in the
requested range therefore cannot generate an executable trade (there is no
"next" candle to fill at), matching how this would work live.

A warm-up buffer of extra history *before* start_date is fetched purely so
the SMA(30) has enough prior data on day one of the requested range — this
is genuine past data relative to every simulated point, not look-ahead.
"""
import math
from datetime import date, datetime, time, timedelta, timezone

from app.core.config import Settings, get_settings
from app.market_data.base import Candle, MarketDataError, MarketDataProvider
from app.market_data.factory import get_market_data_provider
from app.market_data.symbols import DEFAULT_SYMBOLS
from app.models.enums import SignalType, TradeSide
from app.strategies.base import BaseStrategy
from app.strategies.sma_crossover import SmaCrossoverStrategy

from app.backtesting.results import BacktestResult, BacktestTradeResult


class BacktestEngine:
    def __init__(
        self,
        provider: MarketDataProvider | None = None,
        strategy: BaseStrategy | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider or get_market_data_provider()
        self.strategy = strategy or SmaCrossoverStrategy()

    def run(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        starting_capital: float,
        transaction_cost_percent: float,
    ) -> BacktestResult:
        symbol = self._validate(symbol, start_date, end_date, starting_capital)
        candles = self.fetch_candles(symbol, start_date, end_date)
        return self.run_with_candles(symbol, candles, start_date, end_date, starting_capital, transaction_cost_percent)

    def run_with_candles(
        self,
        symbol: str,
        candles: list[Candle],
        start_date: date,
        end_date: date,
        starting_capital: float,
        transaction_cost_percent: float,
    ) -> BacktestResult:
        """Simulate against already-fetched candles — lets a comparison run
        fetch each stock's data once and reuse it across every strategy
        configuration, instead of one fetch per configuration."""
        symbol = self._validate(symbol, start_date, end_date, starting_capital)
        in_scope_candles = [c for c in candles if c.timestamp.date() >= start_date]
        if not in_scope_candles:
            raise MarketDataError(f"No trading data available for {symbol} between {start_date} and {end_date}.")
        return self._simulate(symbol, candles, start_date, end_date, starting_capital, transaction_cost_percent)

    def fetch_candles(self, symbol: str, start_date: date, end_date: date) -> list[Candle]:
        """Fetch real historical data covering the requested range plus a
        warm-up buffer sized to this engine's strategy."""
        warmup_days = self.strategy.warmup_period * 3 + 15  # generous buffer for weekends/holidays
        fetch_start = datetime.combine(start_date, time.min, tzinfo=timezone.utc) - timedelta(days=warmup_days)
        fetch_end = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

        candles = self.provider.get_historical_data(symbol, interval="1d", start=fetch_start, end=fetch_end)
        if not candles:
            raise MarketDataError(f"No historical data available for {symbol} in the requested range.")
        return candles

    @staticmethod
    def _validate(symbol: str, start_date: date, end_date: date, starting_capital: float) -> str:
        symbol = symbol.upper()
        if symbol not in DEFAULT_SYMBOLS:
            raise ValueError(f"Unknown symbol '{symbol}'. Configured symbols: {DEFAULT_SYMBOLS}")
        if end_date <= start_date:
            raise ValueError("end_date must be after start_date")
        if starting_capital <= 0:
            raise ValueError("starting_capital must be positive")
        return symbol

    def _simulate(
        self,
        symbol: str,
        candles: list[Candle],
        start_date: date,
        end_date: date,
        starting_capital: float,
        transaction_cost_percent: float,
    ) -> BacktestResult:
        cash = starting_capital
        quantity = 0
        entry_price: float | None = None
        trades: list[BacktestTradeResult] = []
        equity_curve: list[float] = []
        pending_signal: SignalType | None = None

        buy_hold_entry_price: float | None = None
        buy_hold_quantity = 0
        buy_hold_cash_remainder = 0.0
        buy_hold_last_close: float | None = None

        cost_multiplier = 1 + (transaction_cost_percent / 100)

        for i, candle in enumerate(candles):
            candle_date = candle.timestamp.date()
            in_scope = start_date <= candle_date <= end_date

            # Execute a signal generated on the PREVIOUS in-scope candle, at
            # THIS candle's open — never at the close that generated it. If
            # this candle falls after end_date, the trade is dropped rather
            # than executed outside the requested window.
            if pending_signal is not None:
                if candle_date <= end_date:
                    exec_price = candle.open
                    if pending_signal == SignalType.BUY and quantity == 0:
                        qty = math.floor(cash / (exec_price * cost_multiplier))
                        if qty >= 1:
                            cost = qty * exec_price * (transaction_cost_percent / 100)
                            cash -= qty * exec_price + cost
                            quantity = qty
                            entry_price = exec_price
                            trades.append(
                                BacktestTradeResult(
                                    side=TradeSide.BUY, quantity=qty, price=exec_price,
                                    transaction_cost=cost, realized_pnl=None, timestamp=candle.timestamp,
                                )
                            )
                    elif pending_signal == SignalType.SELL and quantity > 0:
                        cost = quantity * exec_price * (transaction_cost_percent / 100)
                        proceeds = quantity * exec_price - cost
                        pnl = (exec_price - entry_price) * quantity - cost
                        cash += proceeds
                        trades.append(
                            BacktestTradeResult(
                                side=TradeSide.SELL, quantity=quantity, price=exec_price,
                                transaction_cost=cost, realized_pnl=pnl, timestamp=candle.timestamp,
                            )
                        )
                        quantity = 0
                        entry_price = None
                pending_signal = None

            if in_scope:
                if buy_hold_entry_price is None:
                    buy_hold_entry_price = candle.open
                    buy_hold_quantity = math.floor(starting_capital / (buy_hold_entry_price * cost_multiplier))
                    bh_cost = buy_hold_quantity * buy_hold_entry_price * (transaction_cost_percent / 100)
                    buy_hold_cash_remainder = starting_capital - buy_hold_quantity * buy_hold_entry_price - bh_cost
                buy_hold_last_close = candle.close

                equity_curve.append(cash + (quantity * candle.close if quantity > 0 else 0.0))

                # Generate a signal from data up to and including THIS close
                # only — never from candles after it. Only bother if a next
                # candle exists to execute at.
                if i + 1 < len(candles):
                    window = candles[: i + 1]
                    signal = self.strategy.generate_signal(symbol, window)
                    if signal.signal_type == SignalType.BUY and quantity == 0:
                        pending_signal = SignalType.BUY
                    elif signal.signal_type == SignalType.SELL and quantity > 0:
                        pending_signal = SignalType.SELL

        ending_capital = equity_curve[-1] if equity_curve else cash
        total_pnl = ending_capital - starting_capital
        total_return_pct = (total_pnl / starting_capital) * 100

        sells = [t for t in trades if t.side == TradeSide.SELL]
        total_trades = len(sells)
        winning_trades = sum(1 for t in sells if (t.realized_pnl or 0) > 0)
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades * 100) if total_trades else 0.0

        max_drawdown_pct = self._max_drawdown(equity_curve)

        buy_hold_value = buy_hold_cash_remainder + buy_hold_quantity * (buy_hold_last_close or 0.0)
        buy_hold_return_pct = ((buy_hold_value - starting_capital) / starting_capital) * 100

        return BacktestResult(
            symbol=symbol,
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
            max_drawdown_pct=max_drawdown_pct,
            buy_hold_return_pct=buy_hold_return_pct,
            transaction_cost_percent=transaction_cost_percent,
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
