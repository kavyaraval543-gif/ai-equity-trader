import type { Position } from "@/types/trading";

export default function PositionsTable({
  positions,
  trailingStopEnabled,
  trailingStopPercent,
}: {
  positions: Position[];
  trailingStopEnabled: boolean;
  trailingStopPercent: number;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Open Positions ({positions.length})
      </h2>
      {positions.length === 0 ? (
        <p className="text-sm text-gray-400">No open positions.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-400">
                <th className="py-1 pr-4">Symbol</th>
                <th className="py-1 pr-4">Qty</th>
                <th className="py-1 pr-4">Entry</th>
                <th className="py-1 pr-4">Current</th>
                <th className="py-1 pr-4">Unrealized P&L</th>
                <th className="py-1 pr-4">Stop Loss</th>
                <th className="py-1 pr-4">Target</th>
                <th className="py-1 pr-4">Peak</th>
                <th className="py-1 pr-4">Trailing Stop</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => {
                const trailingStopPrice = trailingStopEnabled
                  ? p.peak_price * (1 - trailingStopPercent / 100)
                  : null;
                return (
                  <tr key={p.id} className="border-t border-border">
                    <td className="py-2 pr-4 font-medium text-gray-100">{p.symbol}</td>
                    <td className="py-2 pr-4 font-mono">{p.quantity}</td>
                    <td className="py-2 pr-4 font-mono">{p.entry_price.toFixed(2)}</td>
                    <td className="py-2 pr-4 font-mono">{p.current_price.toFixed(2)}</td>
                    <td className={`py-2 pr-4 font-mono ${p.unrealized_pnl >= 0 ? "text-positive" : "text-negative"}`}>
                      {p.unrealized_pnl.toFixed(2)}
                    </td>
                    <td className="py-2 pr-4 font-mono text-gray-400">{p.stop_loss?.toFixed(2) ?? "—"}</td>
                    <td className="py-2 pr-4 font-mono text-gray-400">{p.target?.toFixed(2) ?? "—"}</td>
                    <td className="py-2 pr-4 font-mono text-gray-400">{p.peak_price.toFixed(2)}</td>
                    <td className="py-2 pr-4 font-mono text-gray-400">
                      {trailingStopPrice !== null ? trailingStopPrice.toFixed(2) : "disabled"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
