import type { TradeSide } from "@/types/trading";

export const BACKTEST_SYMBOLS = ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK"] as const;
export type BacktestSymbol = (typeof BACKTEST_SYMBOLS)[number];

export type StrategyKind = "SMA" | "RSI";

export interface SmaParams {
  short_window: number;
  long_window: number;
}

export interface RsiParams {
  period: number;
  oversold: number;
  overbought: number;
}

export interface BacktestCreateRequest {
  symbol: string;
  start_date: string;
  end_date: string;
  starting_capital: number;
  transaction_cost_percent: number;
  strategy: StrategyKind;
  strategy_params: SmaParams | RsiParams;
}

export interface BacktestRun {
  id: number;
  symbol: string;
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
  max_drawdown_pct: number;
  buy_hold_return_pct: number;
  transaction_cost_percent: number;
  strategy_name: string;
  strategy_params: Record<string, number>;
  created_at: string;
}

export interface BacktestTrade {
  id: number;
  backtest_run_id: number;
  symbol: string;
  side: TradeSide;
  quantity: number;
  price: number;
  transaction_cost: number;
  realized_pnl: number | null;
  timestamp: string;
}

export interface CompareRequest {
  symbol: string;
  start_date: string;
  end_date: string;
  starting_capital: number;
  transaction_cost_percent: number;
}

export interface StrategyComparisonResult {
  backtest_run_id: number | null;
  symbol: string;
  strategy_name: string;
  strategy_params: Record<string, number>;
  total_return_pct: number;
  ending_capital: number;
  total_trades: number;
  win_rate: number;
  max_drawdown_pct: number;
  buy_hold_return_pct: number;
}

export interface CompareResponse {
  symbol: string;
  start_date: string;
  end_date: string;
  starting_capital: number;
  transaction_cost_percent: number;
  results: StrategyComparisonResult[];
  disclaimer: string;
}

export interface MultiStockCompareRequest {
  start_date: string;
  end_date: string;
  starting_capital: number;
  transaction_cost_percent: number;
}

export interface MultiStockStrategyAverage {
  strategy_name: string;
  strategy_params: Record<string, number>;
  avg_return_pct: number;
  avg_max_drawdown_pct: number;
  avg_buy_hold_return_pct: number;
  per_stock: StrategyComparisonResult[];
}

export interface MultiStockCompareResponse {
  start_date: string;
  end_date: string;
  starting_capital: number;
  transaction_cost_percent: number;
  symbols: string[];
  averages: MultiStockStrategyAverage[];
  disclaimer: string;
}
