import type { IntradayBacktestRun } from "@/types/intraday";

function formatMoney(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
}

function pnlClass(n: number): string {
  if (n > 0) return "text-positive";
  if (n < 0) return "text-negative";
  return "text-gray-300";
}

export default function IntradayBacktestResultsSummary({ run }: { run: IntradayBacktestRun }) {
  const items: [string, string, string?][] = [
    ["Starting Capital", formatMoney(run.starting_capital)],
    ["Ending Capital", formatMoney(run.ending_capital)],
    ["Total Return (net)", `${run.total_return_pct >= 0 ? "+" : ""}${run.total_return_pct.toFixed(2)}%`, pnlClass(run.total_return_pct)],
    ["Net P&L", `${run.total_pnl >= 0 ? "+" : ""}${formatMoney(run.total_pnl)}`, pnlClass(run.total_pnl)],
    ["Total Trades", String(run.total_trades)],
    ["Trades / Day", run.trades_per_day.toFixed(2)],
    ["Trading Days", String(run.trading_days)],
    ["Winning Trades", String(run.winning_trades), "text-positive"],
    ["Losing Trades", String(run.losing_trades), "text-negative"],
    ["Win Rate", `${run.win_rate.toFixed(1)}%`],
    ["Avg Win", formatMoney(run.avg_win), "text-positive"],
    ["Avg Loss", formatMoney(run.avg_loss), "text-negative"],
    ["Profit Factor", run.profit_factor == null ? "—" : run.profit_factor.toFixed(2)],
    ["Longest Losing Streak", String(run.longest_losing_streak)],
    ["Maximum Drawdown", `${run.max_drawdown_pct.toFixed(2)}%`, "text-negative"],
    ["Transaction Cost", `${run.transaction_cost_percent}%`],
    ["Slippage", `${run.slippage_percent}%`],
  ];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-1 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Results — {run.symbol} · {run.interval} · {run.strategy_name} ({run.start_date} to {run.end_date})
      </h2>
      <p className="mb-3 text-xs text-gray-500">{run.net_of_costs_note}</p>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
        {items.map(([label, value, cls]) => (
          <div key={label}>
            <dt className="text-xs text-gray-400">{label}</dt>
            <dd className={`font-mono text-lg ${cls ?? "text-gray-100"}`}>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-4 text-xs text-gray-500">{run.disclaimer}</p>
    </div>
  );
}
