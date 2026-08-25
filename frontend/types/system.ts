export interface SystemStatus {
  backend: string;
  database: string;
  trading_mode: string;
  emergency_stop: boolean;
  market_data_provider: string;
  environment: string;
  time: string;
}
