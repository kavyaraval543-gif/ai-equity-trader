"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type {
  AutonomousStatus,
  MarketDataStatus,
  Position,
  RiskDecision,
  RunCycleResult,
  Signal,
  SystemEvent,
  Trade,
  TradingStatus,
} from "@/types/trading";
import PortfolioSummaryCard from "@/components/PortfolioSummaryCard";
import PositionsTable from "@/components/PositionsTable";
import SignalsTable from "@/components/SignalsTable";
import RiskDecisionsTable from "@/components/RiskDecisionsTable";
import TradesTable from "@/components/TradesTable";
import MarketDataStatusCard from "@/components/MarketDataStatusCard";
import AutonomousControlCard from "@/components/AutonomousControlCard";
import MarketSessionCard from "@/components/MarketSessionCard";
import PositionMonitoringSummaryCard from "@/components/PositionMonitoringSummaryCard";
import SystemEventsList from "@/components/SystemEventsList";

const AUTO_REFRESH_INTERVAL_MS = 20_000;

interface DashboardData {
  tradingStatus: TradingStatus;
  positions: Position[];
  signals: Signal[];
  riskDecisions: RiskDecision[];
  trades: Trade[];
  marketDataStatus: MarketDataStatus;
  systemEvents: SystemEvent[];
}

async function fetchAll(): Promise<DashboardData> {
  const [tradingStatus, positions, signals, riskDecisions, trades, marketDataStatus, systemEvents] =
    await Promise.all([
      apiGet<TradingStatus>("/api/v1/trading/status"),
      apiGet<Position[]>("/api/v1/portfolio/positions"),
      apiGet<Signal[]>("/api/v1/signals?limit=50&strategy_name=SMA_CROSSOVER"),
      apiGet<RiskDecision[]>("/api/v1/risk/decisions?limit=50&strategy_name=SMA_CROSSOVER"),
      apiGet<Trade[]>("/api/v1/trades?limit=50"),
      apiGet<MarketDataStatus>("/api/v1/market-data/status"),
      apiGet<SystemEvent[]>("/api/v1/system/events?limit=30"),
    ]);
  return { tradingStatus, positions, signals, riskDecisions, trades, marketDataStatus, systemEvents };
}

export default function TradingDashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [controlBusy, setControlBusy] = useState(false);
  const [lastCycle, setLastCycle] = useState<RunCycleResult | null>(null);
  const fetchInFlight = useRef(false);

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
      const result = await apiPost<RunCycleResult>("/api/v1/trading/run-cycle");
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
        await apiPost<AutonomousStatus>(`/api/v1/trading/autonomous/${path}`);
        await refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setControlBusy(false);
      }
    },
    [refresh]
  );

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-accent/40 bg-accent/10 p-3 text-center text-sm font-semibold tracking-wide text-accent">
        PAPER TRADING ONLY — NO REAL ORDERS
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-surface p-4">
        <div className="text-sm text-gray-400">
          {data ? (
            <>
              Strategy: <span className="text-gray-100">{data.tradingStatus.strategy_names.join(", ")}</span> ·
              {" "}Provider: <span className="text-gray-100">{data.tradingStatus.market_data_provider}</span> ·{" "}
              Emergency stop:{" "}
              <span className={data.tradingStatus.emergency_stop ? "text-negative" : "text-positive"}>
                {data.tradingStatus.emergency_stop ? "ACTIVE" : "off"}
              </span>
            </>
          ) : (
            "Loading trading status…"
          )}
        </div>
        <button
          onClick={runCycle}
          disabled={running}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent/80 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "Running cycle…" : "Run Trading Cycle"}
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-negative/40 bg-negative/10 p-3 text-sm text-negative">{error}</div>
      )}

      {lastCycle && (
        <div className="rounded-lg border border-border bg-surface p-4 text-sm text-gray-300">
          Last cycle: {lastCycle.signals_generated} signal(s), {lastCycle.trades_executed} trade(s) executed,{" "}
          {lastCycle.errors} error(s) — completed{" "}
          {new Date(lastCycle.completed_at).toLocaleTimeString("en-IN")}.
        </div>
      )}

      {data ? (
        <>
          <AutonomousControlCard
            status={data.tradingStatus.autonomous}
            onStart={() => runAutonomousControl("start")}
            onPause={() => runAutonomousControl("pause")}
            onStop={() => runAutonomousControl("stop")}
            busy={controlBusy}
          />
          <MarketSessionCard session={data.tradingStatus.market_session} />
          <PortfolioSummaryCard portfolio={data.tradingStatus.portfolio} />
          <PositionsTable
            positions={data.positions}
            trailingStopEnabled={data.tradingStatus.exit_config.trailing_stop_enabled}
            trailingStopPercent={data.tradingStatus.exit_config.trailing_stop_percent}
          />
          <PositionMonitoringSummaryCard
            autonomous={data.tradingStatus.autonomous}
            exitConfig={data.tradingStatus.exit_config}
            monitoredCount={data.positions.length}
          />
          <SignalsTable signals={data.signals} />
          <RiskDecisionsTable
            decisions={data.riskDecisions}
            signalsById={new Map(data.signals.map((s) => [s.id, s]))}
          />
          <TradesTable trades={data.trades} />
          <MarketDataStatusCard status={data.marketDataStatus} />
          <SystemEventsList events={data.systemEvents} />
        </>
      ) : (
        !error && <p className="text-sm text-gray-400">Loading dashboard…</p>
      )}
    </div>
  );
}
