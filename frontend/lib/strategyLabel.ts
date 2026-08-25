export function formatStrategyLabel(strategyName: string, params: Record<string, number>): string {
  if (strategyName === "BUY_AND_HOLD") return "Buy & Hold";
  if (strategyName === "SMA_CROSSOVER") {
    return `SMA ${params.short_window}/${params.long_window}`;
  }
  if (strategyName === "RSI") {
    return `RSI(${params.period}, ${params.oversold}/${params.overbought})`;
  }
  return strategyName;
}
