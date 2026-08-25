export interface Portfolio {
  id: number;
  starting_capital: number;
  available_cash: number;
  current_equity: number;
  realized_pnl: number;
  unrealized_pnl: number;
  total_pnl: number;
  created_at: string;
  updated_at: string;
}

export type PositionStatus = "OPEN" | "CLOSED";

export interface Position {
  id: number;
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  stop_loss: number | null;
  target: number | null;
  peak_price: number;
  unrealized_pnl: number;
  status: PositionStatus;
  opened_at: string;
  closed_at: string | null;
}

export type TradeSide = "BUY" | "SELL";

export type ExitReason =
  | "STOP_LOSS"
  | "TARGET_REACHED"
  | "TRAILING_STOP"
  | "STRATEGY_EXIT"
  | "SESSION_END"
  | "MANUAL";

export interface Trade {
  id: number;
  symbol: string;
  side: TradeSide;
  quantity: number;
  price: number;
  transaction_cost: number;
  realized_pnl: number | null;
  strategy_name: string;
  exit_reason: ExitReason | null;
  timestamp: string;
}

export type SignalType = "BUY" | "SELL" | "HOLD";

export interface Signal {
  id: number;
  symbol: string;
  signal_type: SignalType;
  confidence: number;
  strategy_name: string;
  reason: string;
  indicator_data: Record<string, number | string>;
  market_price: number;
  timestamp: string;
}

export type RiskDecisionType = "APPROVED" | "REJECTED";

export interface RiskDecision {
  id: number;
  signal_id: number;
  decision: RiskDecisionType;
  reason: string;
  timestamp: string;
}

export interface SymbolMarketDataStatus {
  symbol: string;
  provider: string;
  connected: boolean;
  last_fetched_at: string | null;
  latest_market_timestamp: string | null;
  stale: boolean;
  detail: string;
}

export interface MarketDataStatus {
  provider: string;
  symbols: SymbolMarketDataStatus[];
}

export type AutonomousTradingState = "RUNNING" | "PAUSED" | "STOPPED" | "ERROR";

export interface AutonomousStatus {
  state: AutonomousTradingState;
  reason: string | null;
  updated_at: string;
  emergency_stop: boolean;
  scheduler_running: boolean;
  trading_cycle_interval_seconds: number;
  position_monitor_interval_seconds: number;
  last_successful_cycle_at: string | null;
  last_failed_cycle_at: string | null;
  last_error: string | null;
  last_skip_reason: string | null;
  last_monitor_run_at: string | null;
  last_monitor_error: string | null;
  open_position_count: number;
}

export type MarketSessionStatusValue =
  | "MARKET_OPEN"
  | "MARKET_CLOSED"
  | "PRE_MARKET"
  | "AFTER_MARKET"
  | "HOLIDAY"
  | "WEEKEND";

export interface MarketSession {
  status: MarketSessionStatusValue;
  current_time: string;
  timezone: string;
  session_start: string;
  session_end: string;
  is_trading_allowed: boolean;
}

export interface ExitConfig {
  stop_loss_percent: number;
  target_percent: number;
  trailing_stop_enabled: boolean;
  trailing_stop_percent: number;
  force_close_at_session_end: boolean;
}

export interface TradingStatus {
  trading_mode: string;
  emergency_stop: boolean;
  strategy_names: string[];
  market_data_provider: string;
  symbols: string[];
  portfolio: Portfolio;
  open_position_count: number;
  autonomous: AutonomousStatus;
  market_session: MarketSession;
  exit_config: ExitConfig;
}

export type SystemEventLevel = "INFO" | "WARNING" | "ERROR";

export interface SystemEvent {
  id: number;
  level: SystemEventLevel;
  category: string;
  message: string;
  details: Record<string, unknown> | null;
  timestamp: string;
}

export interface SymbolCycleResult {
  symbol: string;
  status: string;
  signal: Signal | null;
  risk_decision: RiskDecision | null;
  trade: Trade | null;
  error: string | null;
}

export interface RunCycleResult {
  started_at: string;
  completed_at: string;
  symbols: SymbolCycleResult[];
  signals_generated: number;
  trades_executed: number;
  errors: number;
  portfolio: Portfolio;
}
