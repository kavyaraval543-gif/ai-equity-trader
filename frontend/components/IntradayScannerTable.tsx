import type { IntradayScanResult } from "@/types/intraday";

function signalClass(signal: string | null): string {
  if (signal === "BUY") return "text-positive";
  if (signal === "SELL") return "text-negative";
  return "text-gray-400";
}

function fmtTime(ts: string | null): string {
  return ts ? new Date(ts).toLocaleTimeString("en-IN") : "—";
}

export default function IntradayScannerTable({ results }: { results: IntradayScanResult[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Intraday Scanner — INTRADAY_VWAP_MOMENTUM
      </h2>
      {results.length === 0 ? (
        <p className="text-sm text-gray-400">No scan results yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-400">
                <th className="py-1 pr-4">Symbol</th>
                <th className="py-1 pr-4">Price</th>
                <th className="py-1 pr-4">State</th>
                <th className="py-1 pr-4">Confidence</th>
                <th className="py-1 pr-4">Trend</th>
                <th className="py-1 pr-4">VWAP</th>
                <th className="py-1 pr-4">RSI</th>
                <th className="py-1 pr-4">Volume</th>
                <th className="py-1 pr-4">Last Bar</th>
                <th className="py-1 pr-4">Reason</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => {
                const d = r.indicator_data;
                return (
                  <tr key={r.symbol} className="border-t border-border align-top">
                    <td className="py-2 pr-4 font-medium text-gray-100">{r.symbol}</td>
                    {r.error ? (
                      <td className="py-2 pr-4 text-negative" colSpan={9}>
                        {r.error}
                      </td>
                    ) : (
                      <>
                        <td className="py-2 pr-4 font-mono">{r.market_price?.toFixed(2) ?? "—"}</td>
                        <td className={`py-2 pr-4 font-semibold ${signalClass(r.signal_type)}`}>
                          {r.signal_type ?? "—"}
                          {r.is_stale && <span className="ml-1 text-xs font-normal text-yellow-400">(stale)</span>}
                        </td>
                        <td className="py-2 pr-4 font-mono">{r.confidence != null ? r.confidence.toFixed(2) : "—"}</td>
                        <td className="py-2 pr-4 font-mono text-xs text-gray-400">
                          {d ? `${d.ema_fast ?? "—"} / ${d.ema_slow ?? "—"}` : "—"}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs text-gray-400">
                          {d ? `${d.vwap ?? "—"} (${d.above_vwap ? "above" : "below"})` : "—"}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs text-gray-400">
                          {d ? `${d.rsi ?? "—"}${d.rsi_in_band ? " ✓" : ""}` : "—"}
                        </td>
                        <td className="py-2 pr-4 font-mono text-xs text-gray-400">
                          {d ? (d.volume_confirmed ? "confirmed" : d.volume_reliable ? "not confirmed" : "unreliable") : "—"}
                        </td>
                        <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs text-gray-400">
                          {fmtTime(r.latest_bar_time)}
                        </td>
                        <td className="max-w-xs py-2 pr-4 text-xs text-gray-400">{r.reason}</td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-3 text-xs text-gray-500">
        Read-only research view — the scanner never places trades. Entries only happen when Autonomous Intraday
        Trading is running and the risk engine approves.
      </p>
    </div>
  );
}
