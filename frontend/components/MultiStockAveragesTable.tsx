import type { MultiStockCompareResponse } from "@/types/backtest";
import { formatStrategyLabel } from "@/lib/strategyLabel";

export default function MultiStockAveragesTable({ comparison }: { comparison: MultiStockCompareResponse }) {
  const bestReturn = Math.max(...comparison.averages.map((a) => a.avg_return_pct));

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Multi-Stock Average — {comparison.symbols.join(", ")} ({comparison.start_date} to {comparison.end_date})
      </h2>
      <p className="mb-3 text-xs text-gray-500">
        Each stock is an independent ₹{comparison.starting_capital.toLocaleString("en-IN")} backtest — not a
        combined portfolio. Values below are the plain average across all 5 stocks. {comparison.disclaimer}
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="text-xs uppercase text-gray-400">
              <th className="py-1 pr-4">Rank</th>
              <th className="py-1 pr-4">Strategy</th>
              <th className="py-1 pr-4">Avg Return</th>
              <th className="py-1 pr-4">Avg Max Drawdown</th>
              <th className="py-1 pr-4">Avg Buy &amp; Hold</th>
            </tr>
          </thead>
          <tbody>
            {comparison.averages.map((a, i) => {
              const isBest = a.avg_return_pct === bestReturn;
              return (
                <tr
                  key={`${a.strategy_name}-${JSON.stringify(a.strategy_params)}`}
                  className={`border-t border-border ${isBest ? "bg-positive/10" : ""}`}
                >
                  <td className="py-2 pr-4 font-mono text-gray-400">#{i + 1}</td>
                  <td className="py-2 pr-4 font-medium text-gray-100">
                    {formatStrategyLabel(a.strategy_name, a.strategy_params)}
                    {isBest && <span className="ml-2 rounded bg-positive/20 px-1.5 py-0.5 text-xs text-positive">best avg return</span>}
                  </td>
                  <td className={`py-2 pr-4 font-mono font-semibold ${a.avg_return_pct >= 0 ? "text-positive" : "text-negative"}`}>
                    {a.avg_return_pct >= 0 ? "+" : ""}
                    {a.avg_return_pct.toFixed(2)}%
                  </td>
                  <td className="py-2 pr-4 font-mono text-negative">{a.avg_max_drawdown_pct.toFixed(2)}%</td>
                  <td className="py-2 pr-4 font-mono text-gray-400">
                    {a.avg_buy_hold_return_pct >= 0 ? "+" : ""}
                    {a.avg_buy_hold_return_pct.toFixed(2)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <details className="mt-4">
        <summary className="cursor-pointer text-xs text-gray-400">Show per-stock breakdown</summary>
        <div className="mt-2 space-y-4">
          {comparison.averages.map((a) => (
            <div key={`${a.strategy_name}-${JSON.stringify(a.strategy_params)}`}>
              <p className="mb-1 text-xs font-semibold text-gray-300">
                {formatStrategyLabel(a.strategy_name, a.strategy_params)}
              </p>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="text-gray-500">
                      <th className="py-1 pr-4">Stock</th>
                      <th className="py-1 pr-4">Return</th>
                      <th className="py-1 pr-4">Max Drawdown</th>
                      <th className="py-1 pr-4">Trades</th>
                    </tr>
                  </thead>
                  <tbody>
                    {a.per_stock.map((r) => (
                      <tr key={r.symbol} className="border-t border-border">
                        <td className="py-1 pr-4 text-gray-300">{r.symbol}</td>
                        <td className={`py-1 pr-4 font-mono ${r.total_return_pct >= 0 ? "text-positive" : "text-negative"}`}>
                          {r.total_return_pct >= 0 ? "+" : ""}
                          {r.total_return_pct.toFixed(2)}%
                        </td>
                        <td className="py-1 pr-4 font-mono text-negative">{r.max_drawdown_pct.toFixed(2)}%</td>
                        <td className="py-1 pr-4 font-mono">{r.total_trades}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
