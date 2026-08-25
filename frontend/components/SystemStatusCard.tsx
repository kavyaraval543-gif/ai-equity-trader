"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import type { SystemStatus } from "@/types/system";

export default function SystemStatusCard() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<SystemStatus>("/api/v1/system/status")
      .then(setStatus)
      .catch((err: Error) => setError(err.message));
  }, []);

  if (error) {
    return (
      <div className="rounded-lg border border-negative/40 bg-surface p-4 text-sm text-negative">
        Backend unreachable: {error}
      </div>
    );
  }

  if (!status) {
    return (
      <div className="rounded-lg border border-border bg-surface p-4 text-sm text-gray-400">
        Loading system status…
      </div>
    );
  }

  const items: [string, string][] = [
    ["Backend", status.backend],
    ["Database", status.database],
    ["Trading mode", status.trading_mode.toUpperCase()],
    ["Emergency stop", status.emergency_stop ? "ACTIVE" : "off"],
    ["Market data provider", status.market_data_provider],
    ["Environment", status.environment],
  ];

  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">
        System Status
      </h2>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
        {items.map(([label, value]) => (
          <div key={label} className="flex justify-between gap-4">
            <dt className="text-gray-400">{label}</dt>
            <dd className="font-mono text-gray-100">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
