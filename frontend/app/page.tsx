import SystemStatusCard from "@/components/SystemStatusCard";
import TradingDashboard from "@/components/TradingDashboard";

export default function HomePage() {
  return (
    <main className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-100">AI Equity Trader</h1>
        <p className="mt-1 text-sm text-gray-400">
          Paper trading only. No real broker credentials or live orders exist in this system.
        </p>
      </div>
      <SystemStatusCard />
      <TradingDashboard />
    </main>
  );
}
