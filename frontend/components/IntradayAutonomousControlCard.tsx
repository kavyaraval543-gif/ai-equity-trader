"use client";

import type { IntradayAutonomousStatus } from "@/types/intraday";

function stateClass(state: IntradayAutonomousStatus["state"]): string {
  if (state === "RUNNING") return "text-positive";
  if (state === "ERROR") return "text-negative";
  if (state === "PAUSED") return "text-yellow-400";
  return "text-gray-400";
}

function fmt(ts: string | null): string {
  return ts ? new Date(ts).toLocaleString("en-IN") : "—";
}

function formatMoney(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
}

export default function IntradayAutonomousControlCard({
  status,
  onStart,
  onPause,
  onStop,
  busy,
}: {
  status: IntradayAutonomousStatus;
  onStart: () => void;
  onPause: () => void;
  onStop: () => void;
  busy: boolean;
}) {
  const maxDailyLoss = status.max_daily_loss_pct; // fraction, e.g. 0.02

  const confirmAndRun = (action: "start" | "pause" | "stop", fn: () => void) => {
    const messages: Record<string, string> = {
      start:
        "Start AUTONOMOUS INTRADAY paper trading? The scheduler will begin looking for new intraday entries on its own interval, completely separate from the daily SMA(10/30) trader.",
      pause: "Pause autonomous intraday trading? New entries will stop, but existing open intraday positions will keep being monitored.",
      stop: "Stop autonomous intraday trading? No new intraday entries will be taken until it is started again.",
    };
    if (window.confirm(messages[action])) {
      fn();
    }
  };

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Autonomous Intraday Trading
      </h2>

      <div className="mb-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        <div>
          <dt className="text-xs text-gray-400">State</dt>
          <dd className={`text-lg font-semibold ${stateClass(status.state)}`}>{status.state}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Open positions</dt>
          <dd className="font-mono text-gray-100">{status.open_position_count}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Cycle interval</dt>
          <dd className="font-mono text-gray-100">{status.cycle_interval_seconds}s</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Monitor interval</dt>
          <dd className="font-mono text-gray-100">{status.position_monitor_interval_seconds}s</dd>
        </div>

        <div>
          <dt className="text-xs text-gray-400">Trades today</dt>
          <dd className={`font-mono ${status.trades_today >= status.max_trades_per_day ? "text-negative" : "text-gray-100"}`}>
            {status.trades_today} / {status.max_trades_per_day}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Daily P&amp;L</dt>
          <dd className={`font-mono ${status.realized_pnl_today >= 0 ? "text-positive" : "text-negative"}`}>
            {formatMoney(status.realized_pnl_today)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Daily loss limit</dt>
          <dd className="font-mono text-gray-100">{(maxDailyLoss * 100).toFixed(1)}%</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Consecutive losses</dt>
          <dd
            className={`font-mono ${
              status.consecutive_losses >= status.max_consecutive_losses ? "text-negative" : "text-gray-100"
            }`}
          >
            {status.consecutive_losses} / {status.max_consecutive_losses}
          </dd>
        </div>

        <div>
          <dt className="text-xs text-gray-400">Last successful cycle</dt>
          <dd className="font-mono text-xs text-gray-100">{fmt(status.last_successful_cycle_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Last monitor run</dt>
          <dd className="font-mono text-xs text-gray-100">{fmt(status.last_monitor_run_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Last failure</dt>
          <dd className="font-mono text-xs text-negative">{status.last_failed_cycle_at ? fmt(status.last_failed_cycle_at) : "none"}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Cooldown</dt>
          <dd className={`font-mono text-xs ${status.in_cooldown ? "text-yellow-400" : "text-gray-100"}`}>
            {status.in_cooldown ? "active" : "clear"}
          </dd>
        </div>
      </div>

      {status.last_error && (
        <p className="mb-3 rounded border border-negative/40 bg-negative/10 p-2 text-xs text-negative">
          Last error: {status.last_error}
        </p>
      )}
      {status.last_skip_reason && status.state !== "RUNNING" && (
        <p className="mb-3 text-xs text-gray-400">Currently skipping new cycles: {status.last_skip_reason}</p>
      )}
      {status.emergency_stop && (
        <p className="mb-3 rounded border border-negative/40 bg-negative/10 p-2 text-xs font-semibold text-negative">
          EMERGENCY STOP ACTIVE — overrides all autonomous controls. No new entries can start.
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => confirmAndRun("start", onStart)}
          disabled={busy || status.state === "RUNNING"}
          className="rounded-md bg-positive/20 px-3 py-1.5 text-sm font-semibold text-positive transition hover:bg-positive/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Start Autonomous Intraday Trading
        </button>
        <button
          onClick={() => confirmAndRun("pause", onPause)}
          disabled={busy || status.state !== "RUNNING"}
          className="rounded-md bg-yellow-500/20 px-3 py-1.5 text-sm font-semibold text-yellow-400 transition hover:bg-yellow-500/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Pause New Trades
        </button>
        <button
          onClick={() => confirmAndRun("stop", onStop)}
          disabled={busy || status.state === "STOPPED"}
          className="rounded-md bg-negative/20 px-3 py-1.5 text-sm font-semibold text-negative transition hover:bg-negative/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Stop Autonomous Intraday Trading
        </button>
      </div>
    </div>
  );
}
