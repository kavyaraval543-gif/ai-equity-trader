"use client";

export type BacktestMode = "single" | "compare";

export default function BacktestModeSelector({
  mode,
  onChange,
}: {
  mode: BacktestMode;
  onChange: (mode: BacktestMode) => void;
}) {
  const tabs: [BacktestMode, string][] = [
    ["single", "Single Backtest"],
    ["compare", "Compare Strategies"],
  ];

  return (
    <div className="flex gap-2">
      {tabs.map(([value, label]) => (
        <button
          key={value}
          onClick={() => onChange(value)}
          className={`rounded-md px-4 py-2 text-sm font-semibold transition ${
            mode === value
              ? "bg-accent text-white"
              : "border border-border bg-surface text-gray-400 hover:text-gray-100"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
