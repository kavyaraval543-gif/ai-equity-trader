"use client";

import { useState } from "react";
import { BACKTEST_SYMBOLS } from "@/types/backtest";

const todayIso = () => new Date().toISOString().slice(0, 10);
const yearsAgoIso = (years: number) => {
  const d = new Date();
  d.setFullYear(d.getFullYear() - years);
  return d.toISOString().slice(0, 10);
};

export default function CompareControls({
  onCompare,
  onCompareMultiStock,
  running,
}: {
  onCompare: (params: {
    symbol: string;
    start_date: string;
    end_date: string;
    starting_capital: number;
    transaction_cost_percent: number;
  }) => void;
  onCompareMultiStock: (params: {
    start_date: string;
    end_date: string;
    starting_capital: number;
    transaction_cost_percent: number;
  }) => void;
  running: boolean;
}) {
  const [symbol, setSymbol] = useState<string>(BACKTEST_SYMBOLS[0]);
  const [startDate, setStartDate] = useState(yearsAgoIso(3));
  const [endDate, setEndDate] = useState(todayIso());
  const [startingCapital, setStartingCapital] = useState(100_000);
  const [transactionCostPercent, setTransactionCostPercent] = useState(0.1);

  const shared = {
    start_date: startDate,
    end_date: endDate,
    starting_capital: startingCapital,
    transaction_cost_percent: transactionCostPercent,
  };

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
        Compare SMA 5/20, 10/30, 20/50, 50/200, RSI(14) &amp; Buy &amp; Hold
      </h2>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
        <div>
          <label className="mb-1 block text-xs text-gray-400">Stock</label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
          >
            {BACKTEST_SYMBOLS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-400">Start Date</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-400">End Date</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-400">Starting Money (₹)</label>
          <input
            type="number"
            min={1}
            value={startingCapital}
            onChange={(e) => setStartingCapital(Number(e.target.value))}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-400">Txn Cost (%)</label>
          <input
            type="number"
            min={0}
            step={0.01}
            value={transactionCostPercent}
            onChange={(e) => setTransactionCostPercent(Number(e.target.value))}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
          />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={() => onCompare({ symbol, ...shared })}
          disabled={running}
          className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent/80 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "Comparing…" : "Compare Strategies"}
        </button>
        <button
          onClick={() => onCompareMultiStock(shared)}
          disabled={running}
          className="rounded-md border border-accent/40 bg-accent/10 px-4 py-2 text-sm font-semibold text-accent transition hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {running ? "Comparing…" : "Compare Across All 5 Stocks"}
        </button>
        <span className="text-xs text-gray-500">
          Multi-stock ignores the Stock dropdown — each of the 5 stocks runs independently at ₹
          {startingCapital.toLocaleString("en-IN")} starting capital.
        </span>
      </div>
    </div>
  );
}
