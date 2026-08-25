"use client";

import { useState } from "react";
import { BACKTEST_SYMBOLS, type BacktestCreateRequest, type StrategyKind } from "@/types/backtest";

const todayIso = () => new Date().toISOString().slice(0, 10);
const yearAgoIso = () => {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 1);
  return d.toISOString().slice(0, 10);
};

export default function BacktestControls({
  onRun,
  running,
}: {
  onRun: (params: BacktestCreateRequest) => void;
  running: boolean;
}) {
  const [symbol, setSymbol] = useState<string>(BACKTEST_SYMBOLS[0]);
  const [startDate, setStartDate] = useState(yearAgoIso());
  const [endDate, setEndDate] = useState(todayIso());
  const [startingCapital, setStartingCapital] = useState(100_000);
  const [transactionCostPercent, setTransactionCostPercent] = useState(0.1);

  const [strategy, setStrategy] = useState<StrategyKind>("SMA");
  const [smaShort, setSmaShort] = useState(10);
  const [smaLong, setSmaLong] = useState(30);
  const [rsiPeriod, setRsiPeriod] = useState(14);
  const [rsiOversold, setRsiOversold] = useState(30);
  const [rsiOverbought, setRsiOverbought] = useState(70);

  const smaInvalid = strategy === "SMA" && smaShort >= smaLong;
  const rsiInvalid = strategy === "RSI" && !(rsiOversold > 0 && rsiOversold < rsiOverbought && rsiOverbought < 100);

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Run a Backtest</h2>
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

      <div className="mt-4 border-t border-border pt-4">
        <label className="mb-1 block text-xs text-gray-400">Strategy</label>
        <div className="flex flex-wrap items-end gap-4">
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value as StrategyKind)}
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
          >
            <option value="SMA">SMA Crossover</option>
            <option value="RSI">RSI</option>
          </select>

          {strategy === "SMA" ? (
            <>
              <div>
                <label className="mb-1 block text-xs text-gray-400">Fast Period</label>
                <input
                  type="number"
                  min={1}
                  value={smaShort}
                  onChange={(e) => setSmaShort(Number(e.target.value))}
                  className="w-24 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-400">Slow Period</label>
                <input
                  type="number"
                  min={1}
                  value={smaLong}
                  onChange={(e) => setSmaLong(Number(e.target.value))}
                  className="w-24 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
                />
              </div>
              {smaInvalid && <p className="text-xs text-negative">Fast period must be less than slow period.</p>}
            </>
          ) : (
            <>
              <div>
                <label className="mb-1 block text-xs text-gray-400">RSI Period</label>
                <input
                  type="number"
                  min={1}
                  value={rsiPeriod}
                  onChange={(e) => setRsiPeriod(Number(e.target.value))}
                  className="w-24 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-400">Oversold</label>
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={rsiOversold}
                  onChange={(e) => setRsiOversold(Number(e.target.value))}
                  className="w-24 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-gray-400">Overbought</label>
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={rsiOverbought}
                  onChange={(e) => setRsiOverbought(Number(e.target.value))}
                  className="w-24 rounded-md border border-border bg-background px-2 py-1.5 text-sm text-gray-100"
                />
              </div>
              {rsiInvalid && (
                <p className="text-xs text-negative">Thresholds must satisfy 0 &lt; oversold &lt; overbought &lt; 100.</p>
              )}
            </>
          )}
        </div>
      </div>

      <button
        onClick={() =>
          onRun({
            symbol,
            start_date: startDate,
            end_date: endDate,
            starting_capital: startingCapital,
            transaction_cost_percent: transactionCostPercent,
            strategy,
            strategy_params:
              strategy === "SMA"
                ? { short_window: smaShort, long_window: smaLong }
                : { period: rsiPeriod, oversold: rsiOversold, overbought: rsiOverbought },
          })
        }
        disabled={running || smaInvalid || rsiInvalid}
        className="mt-4 rounded-md bg-accent px-4 py-2 text-sm font-semibold text-white transition hover:bg-accent/80 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {running ? "Running backtest…" : "Run Backtest"}
      </button>
    </div>
  );
}
