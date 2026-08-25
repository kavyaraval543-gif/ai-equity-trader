import type { MarketSession } from "@/types/trading";

function statusClass(status: MarketSession["status"]): string {
  if (status === "MARKET_OPEN") return "text-positive";
  if (status === "PRE_MARKET" || status === "AFTER_MARKET") return "text-yellow-400";
  return "text-gray-400";
}

export default function MarketSessionCard({ session }: { session: MarketSession }) {
  const items: [string, string][] = [
    ["Current time (IST)", new Date(session.current_time).toLocaleString("en-IN", { timeZone: session.timezone })],
    ["Configured session", `${session.session_start} – ${session.session_end} (${session.timezone})`],
    ["Trading allowed now", session.is_trading_allowed ? "yes" : "no"],
  ];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Market Session</h2>
      <div className={`mb-3 text-lg font-semibold ${statusClass(session.status)}`}>
        {session.status.replace("_", " ")}
      </div>
      <dl className="grid grid-cols-1 gap-2 sm:grid-cols-3">
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
