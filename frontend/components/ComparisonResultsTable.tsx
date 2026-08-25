import type { CompareResponse } from "@/types/backtest";
import { formatStrategyLabel } from "@/lib/strategyLabel";

function formatMoney(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
}

export default function ComparisonResultsTable({ comparison }: { comparison: CompareResponse }) {
  const bestReturn = Math.max(...comparison.results.map((r) => r.total_return_pct));

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Strategy Comparison — {comparison.symbol} ({comparison.start_date} to {comparison.end_date})
      </h2>
      <p className="mb-3 text-xs text-gray-500">{comparison.disclaimer}</p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs uppercase text-gray-400">
              <th className="py-1 pr-4">Rank</th>
              <th className="py-1 pr-4">Strategy</th>
              <th className="py-1 pr-4">Parameters</th>
              <th className="py-1 pr-4">Return</th>
              <th className="py-1 pr-4">Final Capital</th>
              <th className="py-1 pr-4">Trades</th>
              <th className="py-1 pr-4">Win Rate</th>
              <th className="py-1 pr-4">Max Drawdown</th>
            </tr>
          </thead>
          <tbody>
            {comparison.results.map((r, i) => {
              const isBest = r.total_return_pct === bestReturn;
              return (
                <tr
                  key={`${r.strategy_name}-${JSON.stringify(r.strategy_params)}`}
                  className={`border-t border-border ${isBest ? "bg-positive/10" : ""}`}
                >
                  <td className="py-2 pr-4 font-mono text-gray-400">#{i + 1}</td>
                  <td className="py-2 pr-4 font-medium text-gray-100">
                    {formatStrategyLabel(r.strategy_name, r.strategy_params)}
                    {isBest && <span className="ml-2 rounded bg-positive/20 px-1.5 py-0.5 text-xs text-positive">best return</span>}
                  </td>
                  <td className="py-2 pr-4 font-mono text-xs text-gray-400">
                    {Object.entries(r.strategy_params).map(([k, v]) => `${k}=${v}`).join(", ") || "—"}
                  </td>
                  <td className={`py-2 pr-4 font-mono font-semibold ${r.total_return_pct >= 0 ? "text-positive" : "text-negative"}`}>
                    {r.total_return_pct >= 0 ? "+" : ""}
                    {r.total_return_pct.toFixed(2)}%
                  </td>
                  <td className="py-2 pr-4 font-mono">{formatMoney(r.ending_capital)}</td>
                  <td className="py-2 pr-4 font-mono">{r.total_trades}</td>
                  <td className="py-2 pr-4 font-mono">{r.win_rate.toFixed(1)}%</td>
                  <td className="py-2 pr-4 font-mono text-negative">{r.max_drawdown_pct.toFixed(2)}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
