"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import type {
  BacktestCreateRequest,
  BacktestRun,
  BacktestTrade,
  CompareResponse,
  MultiStockCompareResponse,
} from "@/types/backtest";
import BacktestControls from "@/components/BacktestControls";
import BacktestResultsSummary from "@/components/BacktestResultsSummary";
import BacktestComparisonCard from "@/components/BacktestComparisonCard";
import BacktestTradesTable from "@/components/BacktestTradesTable";
import PreviousBacktestsList from "@/components/PreviousBacktestsList";
import BacktestModeSelector, { type BacktestMode } from "@/components/BacktestModeSelector";
import CompareControls from "@/components/CompareControls";
import ComparisonResultsTable from "@/components/ComparisonResultsTable";
import MultiStockAveragesTable from "@/components/MultiStockAveragesTable";

export default function BacktestingDashboard() {
  const [mode, setMode] = useState<BacktestMode>("single");

  const [runs, setRuns] = useState<BacktestRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<BacktestRun | null>(null);
  const [selectedTrades, setSelectedTrades] = useState<BacktestTrade[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [comparison, setComparison] = useState<CompareResponse | null>(null);
  const [multiStockComparison, setMultiStockComparison] = useState<MultiStockCompareResponse | null>(null);

  const refreshRuns = useCallback(async () => {
    try {
      setRuns(await apiGet<BacktestRun[]>("/api/v1/backtests"));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    refreshRuns();
  }, [refreshRuns]);

  const selectRun = useCallback(async (id: number) => {
    setError(null);
    try {
      const [run, trades] = await Promise.all([
        apiGet<BacktestRun>(`/api/v1/backtests/${id}`),
        apiGet<BacktestTrade[]>(`/api/v1/backtests/${id}/trades`),
      ]);
      setSelectedRun(run);
      setSelectedTrades(trades);
      setComparison(null);
      setMultiStockComparison(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const runBacktest = useCallback(
    async (params: BacktestCreateRequest) => {
      setRunning(true);
      setError(null);
      try {
        const run = await apiPost<BacktestRun>("/api/v1/backtests", params);
        await refreshRuns();
        await selectRun(run.id);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setRunning(false);
      }
    },
    [refreshRuns, selectRun]
  );

  const runCompare = useCallback(
    async (params: { symbol: string; start_date: string; end_date: string; starting_capital: number; transaction_cost_percent: number }) => {
      setRunning(true);
      setError(null);
      setSelectedRun(null);
      setMultiStockComparison(null);
      try {
        const result = await apiPost<CompareResponse>("/api/v1/backtests/compare", params);
        setComparison(result);
        await refreshRuns();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setRunning(false);
      }
    },
    [refreshRuns]
  );

  const runCompareMultiStock = useCallback(
    async (params: { start_date: string; end_date: string; starting_capital: number; transaction_cost_percent: number }) => {
      setRunning(true);
      setError(null);
      setSelectedRun(null);
      setComparison(null);
      try {
        const result = await apiPost<MultiStockCompareResponse>("/api/v1/backtests/compare-multi-stock", params);
        setMultiStockComparison(result);
        await refreshRuns();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setRunning(false);
      }
    },
    [refreshRuns]
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">📊 Backtesting</h1>
        <p className="mt-1 text-sm text-gray-400">
          See how strategies would have performed on real historical data. Simulation only — this never touches
          the live paper-trading portfolio, and results are historical, not a promise of future performance.
        </p>
      </div>

      <BacktestModeSelector mode={mode} onChange={setMode} />

      {mode === "single" ? (
        <BacktestControls onRun={runBacktest} running={running} />
      ) : (
        <CompareControls onCompare={runCompare} onCompareMultiStock={runCompareMultiStock} running={running} />
      )}

      {error && (
        <div className="rounded-lg border border-negative/40 bg-negative/10 p-3 text-sm text-negative">{error}</div>
      )}

      {mode === "single" && selectedRun && (
        <>
          <BacktestResultsSummary run={selectedRun} />
          <BacktestComparisonCard run={selectedRun} />
          <BacktestTradesTable trades={selectedTrades} />
        </>
      )}

      {mode === "compare" && comparison && <ComparisonResultsTable comparison={comparison} />}
      {mode === "compare" && multiStockComparison && <MultiStockAveragesTable comparison={multiStockComparison} />}

      <PreviousBacktestsList runs={runs} onSelect={selectRun} selectedId={selectedRun?.id ?? null} />
    </div>
  );
}
