import type { BacktestRun } from "@/types/backtest";

export default function BacktestComparisonCard({ run }: { run: BacktestRun }) {
  const strategyWon = run.total_return_pct > run.buy_hold_return_pct;
  const tie = run.total_return_pct === run.buy_hold_return_pct;

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Strategy vs. Buy &amp; Hold
      </h2>
      <div className="space-y-2">
        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <span className="text-sm text-gray-300">OUR SMA STRATEGY</span>
          <span className={`font-mono text-lg font-semibold ${run.total_return_pct >= 0 ? "text-positive" : "text-negative"}`}>
            {run.total_return_pct >= 0 ? "+" : ""}
            {run.total_return_pct.toFixed(2)}%
          </span>
        </div>
        <div className="flex items-center justify-between rounded-md border border-border p-3">
          <span className="text-sm text-gray-300">BUY &amp; HOLD</span>
          <span className={`font-mono text-lg font-semibold ${run.buy_hold_return_pct >= 0 ? "text-positive" : "text-negative"}`}>
            {run.buy_hold_return_pct >= 0 ? "+" : ""}
            {run.buy_hold_return_pct.toFixed(2)}%
          </span>
        </div>
      </div>
      <p className="mt-3 text-sm">
        {tie ? (
          <span className="text-gray-400">Both approaches performed identically over this period.</span>
        ) : strategyWon ? (
          <span className="text-positive">
            The SMA strategy outperformed buy &amp; hold by{" "}
            {(run.total_return_pct - run.buy_hold_return_pct).toFixed(2)} percentage points over this period.
          </span>
        ) : (
          <span className="text-negative">
            Buy &amp; hold outperformed the SMA strategy by{" "}
            {(run.buy_hold_return_pct - run.total_return_pct).toFixed(2)} percentage points over this period.
          </span>
        )}
      </p>
      <p className="mt-2 text-xs text-gray-500">
        Past performance over one historical period is not a guarantee of future results.
      </p>
    </div>
  );
}
