"use client";

import { useState } from "react";
import { INTRADAY_INTERVALS, INTRADAY_SYMBOLS, type IntradayBacktestCreateRequest, type IntradayInterval } from "@/types/intraday";

const todayIso = () => new Date().toISOString().slice(0, 10);
const daysAgoIso = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
};

export default function IntradayBacktestControls({
  onRun,
  running,
}: {
  onRun: (params: IntradayBacktestCreateRequest) => void;
  running: boolean;
}) {
  const [symbol, setSymbol] = useState<string>(INTRADAY_SYMBOLS[0]);
  const [interval, setInterval] = useState<IntradayInterval>("5m");
  const [startDate, setStartDate] = useState(daysAgoIso(20));
  const [endDate, setEndDate] = useState(todayIso());
  const [startingCapital, setStartingCapital] = useState(100_000);
  const [transactionCostPercent, setTransactionCostPercent] = useState(0.05);
  const [slippagePercent, setSlippagePercent] = useState(0.05);

  const dateInvalid = new Date(endDate) <= new Date(startDate);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Run an Intraday Backtest</h2>
      <p className="mb-3 text-xs text-gray-500">
        The real-time data provider only supports 5m/15m history within the last 60 days — pick a recent date range.
      </p>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 lg:grid-cols-7">
        <div>
          <label className="mb-1 block text-xs text-gray-400">Stock</label>
          <select
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
          >
            {INTRADAY_SYMBOLS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs text-gray-400">Interval</label>
          <select
            value={interval}
            onChange={(e) => setInterval(e.target.value as IntradayInterval)}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
          >
            {INTRADAY_INTERVALS.map((i) => (
              <option key={i} value={i}>
                {i}
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
        <div>
          <label className="mb-1 block text-xs text-gray-400">Slippage (%)</label>
          <input
            type="number"
            min={0}
            step={0.01}
            value={slippagePercent}
            onChange={(e) => setSlippagePercent(Number(e.target.value))}
            className="w-full rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
          />
        </div>
      </div>

      {dateInvalid && <p className="mt-2 text-xs text-negative">End date must be after start date.</p>}

      <button
        onClick={() =>
          onRun({
            symbol,
            interval,
            start_date: startDate,
            end_date: endDate,
            starting_capital: startingCapital,
            transaction_cost_percent: transactionCostPercent,
            slippage_percent: slippagePercent,
          })
        }
        disabled={running || dateInvalid}
        className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent/80 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {running ? "Running intraday backtest…" : "Run Intraday Backtest"}
      </button>
    </div>
  );
}
