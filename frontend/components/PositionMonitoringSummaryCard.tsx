import type { AutonomousStatus, ExitConfig } from "@/types/trading";

export default function PositionMonitoringSummaryCard({
  autonomous,
  exitConfig,
  monitoredCount,
}: {
  autonomous: AutonomousStatus;
  exitConfig: ExitConfig;
  monitoredCount: number;
}) {
  const items: [string, string][] = [
    ["Monitored positions", String(monitoredCount)],
    ["Last update", autonomous.last_monitor_run_at ? new Date(autonomous.last_monitor_run_at).toLocaleTimeString("en-IN") : "—"],
    ["Monitor interval", `${autonomous.position_monitor_interval_seconds}s`],
    ["Stop loss", `${exitConfig.stop_loss_percent}%`],
    ["Target", `${exitConfig.target_percent}%`],
    [
      "Trailing stop",
      exitConfig.trailing_stop_enabled ? `enabled (${exitConfig.trailing_stop_percent}%)` : "disabled",
    ],
    ["Force close at session end", exitConfig.force_close_at_session_end ? "enabled" : "disabled"],
  ];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Position Monitoring</h2>
      {autonomous.last_monitor_error && (
        <p className="mb-3 rounded border border-negative/40 bg-negative/10 p-2 text-xs text-negative">
          Last monitor error: {autonomous.last_monitor_error}
        </p>
      )}
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
        {items.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-gray-400">{label}</dt>
            <dd className="font-mono text-sm text-gray-100">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
