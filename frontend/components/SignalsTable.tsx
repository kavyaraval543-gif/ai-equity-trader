import type { Signal } from "@/types/trading";

function signalClass(type: Signal["signal_type"]): string {
  if (type === "BUY") return "text-positive";
  if (type === "SELL") return "text-negative";
  return "text-gray-400";
}

export default function SignalsTable({ signals }: { signals: Signal[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Recent Signals</h2>
      {signals.length === 0 ? (
        <p className="text-sm text-gray-400">No signals generated yet — run a trading cycle.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-400">
                <th className="py-1 pr-4">Time</th>
                <th className="py-1 pr-4">Symbol</th>
                <th className="py-1 pr-4">Signal</th>
                <th className="py-1 pr-4">Confidence</th>
                <th className="py-1 pr-4">Strategy</th>
                <th className="py-1 pr-4">Reason</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s) => (
                <tr key={s.id} className="border-t border-border align-top">
                  <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs text-gray-400">
                    {new Date(s.timestamp).toLocaleString("en-IN")}
                  </td>
                  <td className="py-2 pr-4 font-medium text-gray-100">{s.symbol}</td>
                  <td className={`py-2 pr-4 font-semibold ${signalClass(s.signal_type)}`}>{s.signal_type}</td>
                  <td className="py-2 pr-4 font-mono">{(s.confidence * 100).toFixed(0)}%</td>
                  <td className="py-2 pr-4 text-gray-400">{s.strategy_name}</td>
                  <td className="py-2 pr-4 text-gray-400">{s.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
