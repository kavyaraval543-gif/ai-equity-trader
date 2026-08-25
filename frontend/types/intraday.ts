import type { ExitReason, MarketSession, Portfolio, SignalType, TradeSide } from "@/types/trading";

export const INTRADAY_SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"] as const;
export const INTRADAY_INTERVALS = ["5m", "15m"] as const;
export type IntradayInterval = (typeof INTRADAY_INTERVALS)[number];

export interface IntradayScanResult {
  symbol: string;
  signal_type: SignalType | null;
  confidence: number | null;
  reason: string | null;
  indicator_data: Record<string, number | string | boolean | null> | null;
  market_price: number | null;
  latest_bar_time: string | null;
  is_stale: boolean;
  error: string | null;
}

export type IntradayAutonomousState = "RUNNING" | "PAUSED" | "STOPPED" | "ERROR";

export interface IntradayAutonomousStatus {
  state: IntradayAutonomousState;
  reason: string | null;
  updated_at: string;
  emergency_stop: boolean;
  scheduler_running: boolean;
  cycle_interval_seconds: number;
  position_monitor_interval_seconds: number;
  last_successful_cycle_at: string | null;
  last_failed_cycle_at: string | null;
  last_error: string | null;
  last_skip_reason: string | null;
  last_monitor_run_at: string | null;
  last_monitor_error: string | null;
  open_position_count: number;
  trades_today: number;
  max_trades_per_day: number;
  realized_pnl_today: number;
  max_daily_loss_pct: number;
  consecutive_losses: number;
  max_consecutive_losses: number;
  in_cooldown: boolean;
}

export interface IntradayExitConfig {
  stop_loss_percent: number;
  target_percent: number;
  trailing_stop_enabled: boolean;
  trailing_stop_percent: number;
  max_holding_minutes: number;
  force_close_at_session_end: boolean;
}

export interface IntradayRiskConfig {
  max_trades_per_day: number;
  max_simultaneous_positions: number;
  max_capital_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_consecutive_losses: number;
  cooldown_minutes: number;
  no_entry_minutes_before_close: number;
}

export interface IntradayTradingStatus {
  trading_mode: string;
  emergency_stop: boolean;
  strategy_names: string[];
  market_data_provider: string;
  symbols: string[];
  interval: string;
  portfolio: Portfolio;
  open_position_count: number;
  autonomous: IntradayAutonomousStatus;
  market_session: MarketSession;
  exit_config: IntradayExitConfig;
  risk_config: IntradayRiskConfig;
}

export interface IntradaySymbolCycleResult {
  symbol: string;
  status: string;
  signal: string | null;
  risk: string | null;
  trade_id: number | null;
  error: string | null;
}

export interface IntradayRunCycleResult {
  started_at: string;
  completed_at: string;
  symbols: IntradaySymbolCycleResult[];
  signals_generated: number;
  trades_executed: number;
  errors: number;
  portfolio: Portfolio;
}

export interface IntradayBacktestCreateRequest {
  symbol: string;
  interval: IntradayInterval;
  start_date: string;
  end_date: string;
  starting_capital: number;
  transaction_cost_percent: number;
  slippage_percent: number;
}

export interface IntradayBacktestTrade {
  side: TradeSide;
  quantity: number;
  price: number;
  transaction_cost: number;
  slippage_cost: number;
  realized_pnl: number | null;
  exit_reason: ExitReason | null;
  timestamp: string;
}

export interface IntradayBacktestRun {
  id: number;
  symbol: string;
  interval: string;
  start_date: string;
  end_date: string;
  starting_capital: number;
  ending_capital: number;
  total_pnl: number;
  total_return_pct: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  win_rate: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number | null;
  max_drawdown_pct: number;
  longest_losing_streak: number;
  trading_days: number;
  trades_per_day: number;
  transaction_cost_percent: number;
  slippage_percent: number;
  strategy_name: string;
  strategy_params: Record<string, number>;
  created_at: string;
  trades: IntradayBacktestTrade[];
  disclaimer: string;
  net_of_costs_note: string;
}
