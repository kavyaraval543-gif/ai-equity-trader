"use client";

import type { AutonomousStatus } from "@/types/trading";

function stateClass(state: AutonomousStatus["state"]): string {
  if (state === "RUNNING") return "text-positive";
  if (state === "ERROR") return "text-negative";
  if (state === "PAUSED") return "text-yellow-400";
  return "text-gray-400";
}

function fmt(ts: string | null): string {
  return ts ? new Date(ts).toLocaleString("en-IN") : "—";
}

export default function AutonomousControlCard({
  status,
  onStart,
  onPause,
  onStop,
  busy,
}: {
  status: AutonomousStatus;
  onStart: () => void;
  onPause: () => void;
  onStop: () => void;
  busy: boolean;
}) {
  const nextCycleEstimate =
    status.state === "RUNNING" && status.last_successful_cycle_at
      ? new Date(
          new Date(status.last_successful_cycle_at).getTime() + status.trading_cycle_interval_seconds * 1000
        ).toLocaleTimeString("en-IN")
      : "—";

  const confirmAndRun = (action: "start" | "pause" | "stop", fn: () => void) => {
    const messages: Record<string, string> = {
      start: "Start autonomous paper trading? The scheduler will begin looking for new entries on its configured interval.",
      pause: "Pause autonomous trading? New entries will stop, but existing open positions will keep being monitored.",
      stop: "Stop autonomous trading? No new entries will be taken until it is started again.",
    };
    if (window.confirm(messages[action])) {
      fn();
    }
  };

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Autonomous Trading</h2>

      <div className="mb-4 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
        <div>
          <dt className="text-xs text-gray-400">State</dt>
          <dd className={`text-lg font-semibold ${stateClass(status.state)}`}>{status.state}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Cycle interval</dt>
          <dd className="font-mono text-gray-100">{status.trading_cycle_interval_seconds}s</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Monitor interval</dt>
          <dd className="font-mono text-gray-100">{status.position_monitor_interval_seconds}s</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Last successful cycle</dt>
          <dd className="font-mono text-xs text-gray-100">{fmt(status.last_successful_cycle_at)}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Next cycle (estimate)</dt>
          <dd className="font-mono text-xs text-gray-100">{nextCycleEstimate}</dd>
        </div>
        <div>
          <dt className="text-xs text-gray-400">Last failure</dt>
          <dd className="font-mono text-xs text-negative">{status.last_failed_cycle_at ? fmt(status.last_failed_cycle_at) : "none"}</dd>
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
          Start Autonomous Trading
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
          Stop Autonomous Trading
        </button>
      </div>
    </div>
  );
}
