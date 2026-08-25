import type { MarketDataStatus } from "@/types/trading";

export default function MarketDataStatusCard({ status }: { status: MarketDataStatus }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Market Data Status — {status.provider}
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs uppercase text-gray-400">
              <th className="py-1 pr-4">Symbol</th>
              <th className="py-1 pr-4">Connected</th>
              <th className="py-1 pr-4">Last Fetched</th>
              <th className="py-1 pr-4">Latest Market Bar</th>
              <th className="py-1 pr-4">Freshness</th>
            </tr>
          </thead>
          <tbody>
            {status.symbols.map((s) => (
              <tr key={s.symbol} className="border-t border-border">
                <td className="py-2 pr-4 font-medium text-gray-100">{s.symbol}</td>
                <td className={`py-2 pr-4 ${s.connected ? "text-positive" : "text-gray-400"}`}>
                  {s.connected ? "yes" : "no"}
                </td>
                <td className="py-2 pr-4 font-mono text-xs text-gray-400">
                  {s.last_fetched_at ? new Date(s.last_fetched_at).toLocaleString("en-IN") : "—"}
                </td>
                <td className="py-2 pr-4 font-mono text-xs text-gray-400">
                  {s.latest_market_timestamp ? new Date(s.latest_market_timestamp).toLocaleString("en-IN") : "—"}
                </td>
                <td className={`py-2 pr-4 font-semibold ${s.stale ? "text-negative" : "text-positive"}`}>
                  {s.stale ? "STALE" : "fresh"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
