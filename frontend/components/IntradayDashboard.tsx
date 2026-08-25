"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type { Position, RiskDecision, Signal, Trade } from "@/types/trading";
import type {
  IntradayAutonomousStatus,
  IntradayBacktestCreateRequest,
  IntradayBacktestRun,
  IntradayRunCycleResult,
  IntradayScanResult,
  IntradayTradingStatus,
} from "@/types/intraday";
import PortfolioSummaryCard from "@/components/PortfolioSummaryCard";
import PositionsTable from "@/components/PositionsTable";
import TradesTable from "@/components/TradesTable";
import SignalsTable from "@/components/SignalsTable";
import RiskDecisionsTable from "@/components/RiskDecisionsTable";
import MarketSessionCard from "@/components/MarketSessionCard";
import IntradayScannerTable from "@/components/IntradayScannerTable";
import IntradayAutonomousControlCard from "@/components/IntradayAutonomousControlCard";
import IntradayBacktestControls from "@/components/IntradayBacktestControls";
import IntradayBacktestResultsSummary from "@/components/IntradayBacktestResultsSummary";
import IntradayBacktestTradesTable from "@/components/IntradayBacktestTradesTable";

const AUTO_REFRESH_INTERVAL_MS = 20_000;

interface DashboardData {
  status: IntradayTradingStatus;
  positions: Position[];
  trades: Trade[];
  scan: IntradayScanResult[];
  signals: Signal[];
  riskDecisions: RiskDecision[];
}

async function fetchAll(): Promise<DashboardData> {
  const [status, positions, trades, scan, signals, riskDecisions] = await Promise.all([
    apiGet<IntradayTradingStatus>("/api/v1/intraday/status"),
    apiGet<Position[]>("/api/v1/intraday/positions"),
    apiGet<Trade[]>("/api/v1/intraday/trades?limit=50"),
    apiGet<IntradayScanResult[]>("/api/v1/intraday/scan"),
    apiGet<Signal[]>("/api/v1/signals?limit=50&strategy_name=INTRADAY_VWAP_MOMENTUM"),
    apiGet<RiskDecision[]>("/api/v1/risk/decisions?limit=50&strategy_name=INTRADAY_VWAP_MOMENTUM"),
  ]);
  return { status, positions, trades, scan, signals, riskDecisions };
}

export default function IntradayDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [controlBusy, setControlBusy] = useState(false);
  const [lastCycle, setLastCycle] = useState<IntradayRunCycleResult | null>(null);
  const fetchInFlight = useRef(false);

  const [backtestRun, setBacktestRun] = useState<IntradayBacktestRun | null>(null);
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [backtestError, setBacktestError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (fetchInFlight.current) return;
    fetchInFlight.current = true;
    try {
      setData(await fetchAll());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      fetchInFlight.current = false;
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, AUTO_REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  const runCycle = useCallback(async () => {
    setRunning(true);
    setError(null);
    try {
      const result = await apiPost<IntradayRunCycleResult>("/api/v1/intraday/run-cycle");
      setLastCycle(result);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setRunning(false);
    }
  }, [refresh]);

  const runAutonomousControl = useCallback(
    async (path: "start" | "pause" | "stop") => {
      setControlBusy(true);
      setError(null);
      try {
        await apiPost<IntradayAutonomousStatus>(`/api/v1/intraday/autonomous/${path}`);
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setControlBusy(false);
      }
    },
    [refresh]
  );

  const runBacktest = useCallback(async (params: IntradayBacktestCreateRequest) => {
    setBacktestRunning(true);
    setBacktestError(null);
    try {
      const run = await apiPost<IntradayBacktestRun>("/api/v1/intraday/backtests", params);
      setBacktestRun(run);
    } catch (err) {
      setBacktestError(err instanceof Error ? err.message : String(err));
    } finally {
      setBacktestRunning(false);
    }
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">⚡ Intraday Trading Research</h1>
        <p className="mt-1 text-sm text-gray-400">
          A separate intraday (5m/15m) research system — its own portfolio, its own strategy
          (INTRADAY_VWAP_MOMENTUM), its own risk rules. It never runs against the daily SMA(10/30) trader&apos;s
          portfolio, and is not enabled automatically.
        </p>
      </div>

      <div className="rounded-lg border border-accent/40 bg-accent/10 p-3 text-center text-sm font-semibold tracking-wide text-accent">
        PAPER TRADING ONLY — NO REAL ORDERS
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4">
        <div className="text-sm text-gray-400">
          {data ? (
            <>
              Strategy: <span className="text-gray-100">{data.status.strategy_names.join(", ")}</span> · Interval:{" "}
              <span className="text-gray-100">{data.status.interval}</span> · Provider:{" "}
              <span className="text-gray-100">{data.status.market_data_provider}</span> · Emergency stop:{" "}
              <span className={data.status.emergency_stop ? "text-negative" : "text-positive"}>
                {data.status.emergency_stop ? "ACTIVE" : "off"}
              </span>
            </>
          ) : (
            "Loading intraday status…"
          )}
        </div>
        <button
          onClick={runCycle}
          disabled={running}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent/80 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "Running cycle…" : "Run Intraday Cycle"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-negative/40 bg-negative/10 p-3 text-sm text-negative">{error}</div>
      )}

      {lastCycle && (
        <div className="rounded-lg border border-border bg-surface p-4 text-sm text-gray-300">
          Last cycle: {lastCycle.signals_generated} signal(s), {lastCycle.trades_executed} trade(s) executed,{" "}
          {lastCycle.errors} error(s) — completed {new Date(lastCycle.completed_at).toLocaleTimeString("en-IN")}.
        </div>
      )}

      {data ? (
        <>
          <IntradayScannerTable results={data.scan} />
          <IntradayAutonomousControlCard
            status={data.status.autonomous}
            onStart={() => runAutonomousControl("start")}
            onPause={() => runAutonomousControl("pause")}
            onStop={() => runAutonomousControl("stop")}
            busy={controlBusy}
          />
          <MarketSessionCard session={data.status.market_session} />
          <PortfolioSummaryCard portfolio={data.status.portfolio} />
          <PositionsTable
            positions={data.positions}
            trailingStopEnabled={data.status.exit_config.trailing_stop_enabled}
            trailingStopPercent={data.status.exit_config.trailing_stop_percent}
          />
          <SignalsTable signals={data.signals} />
          <RiskDecisionsTable
            decisions={data.riskDecisions}
            signalsById={new Map(data.signals.map((s) => [s.id, s]))}
          />
          <TradesTable trades={data.trades} />
        </>
      ) : (
        !error && <p className="text-sm text-gray-400">Loading intraday dashboard…</p>
      )}

      <div className="border-t border-border pt-6">
        <h2 className="mb-3 text-lg font-semibold text-gray-100">Intraday Backtesting</h2>
        <div className="space-y-6">
          <IntradayBacktestControls onRun={runBacktest} running={backtestRunning} />
          {backtestError && (
            <div className="rounded-lg border border-negative/40 bg-negative/10 p-3 text-sm text-negative">
              {backtestError}
            </div>
          )}
          {backtestRun && (
            <>
              <IntradayBacktestResultsSummary run={backtestRun} />
              <IntradayBacktestTradesTable trades={backtestRun.trades} />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
