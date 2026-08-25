import type { BacktestTrade } from "@/types/backtest";

export default function BacktestTradesTable({ trades }: { trades: BacktestTrade[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Trade History</h2>
      {trades.length === 0 ? (
        <p className="text-sm text-gray-400">No trades in this backtest.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-400">
                <th className="py-1 pr-4">Date</th>
                <th className="py-1 pr-4">Action</th>
                <th className="py-1 pr-4">Price</th>
                <th className="py-1 pr-4">Quantity</th>
                <th className="py-1 pr-4">Cost</th>
                <th className="py-1 pr-4">P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-t border-border">
                  <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs text-gray-400">
                    {new Date(t.timestamp).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" })}
                  </td>
                  <td className={`py-2 pr-4 font-semibold ${t.side === "BUY" ? "text-positive" : "text-negative"}`}>
                    {t.side}
                  </td>
                  <td className="py-2 pr-4 font-mono">₹{t.price.toFixed(2)}</td>
                  <td className="py-2 pr-4 font-mono">{t.quantity}</td>
                  <td className="py-2 pr-4 font-mono text-gray-400">₹{t.transaction_cost.toFixed(2)}</td>
                  <td
                    className={`py-2 pr-4 font-mono ${
                      t.realized_pnl == null ? "text-gray-500" : t.realized_pnl >= 0 ? "text-positive" : "text-negative"
                    }`}
                  >
                    {t.realized_pnl == null ? "—" : `${t.realized_pnl >= 0 ? "+" : ""}₹${t.realized_pnl.toFixed(2)}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
