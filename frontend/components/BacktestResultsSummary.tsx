import type { BacktestRun } from "@/types/backtest";
import { formatStrategyLabel } from "@/lib/strategyLabel";

function formatMoney(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
}

function pnlClass(n: number): string {
  if (n > 0) return "text-positive";
  if (n < 0) return "text-negative";
  return "text-gray-300";
}

export default function BacktestResultsSummary({ run }: { run: BacktestRun }) {
  const items: [string, string, string?][] = [
    ["Starting Capital", formatMoney(run.starting_capital)],
    ["Ending Capital", formatMoney(run.ending_capital)],
    ["Total Return", `${run.total_return_pct >= 0 ? "+" : ""}${run.total_return_pct.toFixed(2)}%`, pnlClass(run.total_return_pct)],
    ["Profit/Loss", `${run.total_pnl >= 0 ? "+" : ""}${formatMoney(run.total_pnl)}`, pnlClass(run.total_pnl)],
    ["Total Trades", String(run.total_trades)],
    ["Winning Trades", String(run.winning_trades), "text-positive"],
    ["Losing Trades", String(run.losing_trades), "text-negative"],
    ["Win Rate", `${run.win_rate.toFixed(1)}%`],
    ["Maximum Drawdown", `${run.max_drawdown_pct.toFixed(2)}%`, "text-negative"],
  ];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Results — {run.symbol} · {formatStrategyLabel(run.strategy_name, run.strategy_params)} ({run.start_date} to{" "}
        {run.end_date})
      </h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">
        {items.map(([label, value, cls]) => (
          <div key={label}>
            <dt className="text-xs text-gray-400">{label}</dt>
            <dd className={`font-mono text-lg ${cls ?? "text-gray-100"}`}>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
