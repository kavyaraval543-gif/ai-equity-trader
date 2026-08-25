import type { BacktestRun } from "@/types/backtest";
import { formatStrategyLabel } from "@/lib/strategyLabel";

export default function PreviousBacktestsList({
  runs,
  onSelect,
  selectedId,
}: {
  runs: BacktestRun[];
  onSelect: (id: number) => void;
  selectedId: number | null;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Previous Backtests</h2>
      {runs.length === 0 ? (
        <p className="text-sm text-gray-400">No backtests run yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-400">
                <th className="py-1 pr-4">Run</th>
                <th className="py-1 pr-4">Symbol</th>
                <th className="py-1 pr-4">Strategy</th>
                <th className="py-1 pr-4">Period</th>
                <th className="py-1 pr-4">Return</th>
                <th className="py-1 pr-4">vs Buy &amp; Hold</th>
                <th className="py-1 pr-4">Trades</th>
                <th className="py-1 pr-4">Created</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr
                  key={r.id}
                  onClick={() => onSelect(r.id)}
                  className={`cursor-pointer border-t border-border transition hover:bg-background ${
                    r.id === selectedId ? "bg-background" : ""
                  }`}
                >
                  <td className="py-2 pr-4 font-mono text-gray-400">#{r.id}</td>
                  <td className="py-2 pr-4 font-medium text-gray-100">{r.symbol}</td>
                  <td className="py-2 pr-4 text-xs text-gray-300">
                    {formatStrategyLabel(r.strategy_name, r.strategy_params)}
                  </td>
                  <td className="py-2 pr-4 text-xs text-gray-400">
                    {r.start_date} → {r.end_date}
                  </td>
                  <td className={`py-2 pr-4 font-mono ${r.total_return_pct >= 0 ? "text-positive" : "text-negative"}`}>
                    {r.total_return_pct >= 0 ? "+" : ""}
                    {r.total_return_pct.toFixed(2)}%
                  </td>
                  <td className="py-2 pr-4 font-mono text-gray-400">
                    {r.total_return_pct > r.buy_hold_return_pct ? "beat it" : "lagged"}
                  </td>
                  <td className="py-2 pr-4 font-mono">{r.total_trades}</td>
                  <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs text-gray-400">
                    {new Date(r.created_at).toLocaleString("en-IN")}
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
