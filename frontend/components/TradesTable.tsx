import type { Trade } from "@/types/trading";

export default function TradesTable({ trades }: { trades: Trade[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Recent Trades (Paper)</h2>
      {trades.length === 0 ? (
        <p className="text-sm text-gray-400">No trades executed yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-400">
                <th className="py-1 pr-4">Time</th>
                <th className="py-1 pr-4">Symbol</th>
                <th className="py-1 pr-4">Side</th>
                <th className="py-1 pr-4">Qty</th>
                <th className="py-1 pr-4">Price</th>
                <th className="py-1 pr-4">Cost</th>
                <th className="py-1 pr-4">Realized P&L</th>
                <th className="py-1 pr-4">Strategy</th>
                <th className="py-1 pr-4">Exit Reason</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-t border-border">
                  <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs text-gray-400">
                    {new Date(t.timestamp).toLocaleString("en-IN")}
                  </td>
                  <td className="py-2 pr-4 font-medium text-gray-100">{t.symbol}</td>
                  <td className={`py-2 pr-4 font-semibold ${t.side === "BUY" ? "text-positive" : "text-negative"}`}>
                    {t.side}
                  </td>
                  <td className="py-2 pr-4 font-mono">{t.quantity}</td>
                  <td className="py-2 pr-4 font-mono">{t.price.toFixed(2)}</td>
                  <td className="py-2 pr-4 font-mono text-gray-400">{t.transaction_cost.toFixed(2)}</td>
                  <td
                    className={`py-2 pr-4 font-mono ${
                      t.realized_pnl == null ? "text-gray-500" : t.realized_pnl >= 0 ? "text-positive" : "text-negative"
                    }`}
                  >
                    {t.realized_pnl == null ? "—" : t.realized_pnl.toFixed(2)}
                  </td>
                  <td className="py-2 pr-4 text-gray-400">{t.strategy_name}</td>
                  <td className="py-2 pr-4 text-gray-400">{t.exit_reason ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
