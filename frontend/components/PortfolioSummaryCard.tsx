import type { Portfolio } from "@/types/trading";

function formatMoney(n: number): string {
  return n.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 2 });
}

function pnlClass(n: number): string {
  if (n > 0) return "text-positive";
  if (n < 0) return "text-negative";
  return "text-gray-300";
}

export default function PortfolioSummaryCard({ portfolio }: { portfolio: Portfolio }) {
  const items: [string, string, string?][] = [
    ["Starting capital", formatMoney(portfolio.starting_capital)],
    ["Current equity", formatMoney(portfolio.current_equity)],
    ["Available cash", formatMoney(portfolio.available_cash)],
    ["Realized P&L", formatMoney(portfolio.realized_pnl), pnlClass(portfolio.realized_pnl)],
    ["Unrealized P&L", formatMoney(portfolio.unrealized_pnl), pnlClass(portfolio.unrealized_pnl)],
    ["Total P&L", formatMoney(portfolio.total_pnl), pnlClass(portfolio.total_pnl)],
  ];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Portfolio</h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3">
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
