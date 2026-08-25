import type { RiskDecision, Signal } from "@/types/trading";

export default function RiskDecisionsTable({
  decisions,
  signalsById,
}: {
  decisions: RiskDecision[];
  signalsById: Map<number, Signal>;
}) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">Risk Decisions</h2>
      {decisions.length === 0 ? (
        <p className="text-sm text-gray-400">No risk decisions yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs uppercase text-gray-400">
                <th className="py-1 pr-4">Time</th>
                <th className="py-1 pr-4">Symbol</th>
                <th className="py-1 pr-4">Decision</th>
                <th className="py-1 pr-4">Reason</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((d) => (
                <tr key={d.id} className="border-t border-border align-top">
                  <td className="py-2 pr-4 whitespace-nowrap font-mono text-xs text-gray-400">
                    {new Date(d.timestamp).toLocaleString("en-IN")}
                  </td>
                  <td className="py-2 pr-4 font-medium text-gray-100">
                    {signalsById.get(d.signal_id)?.symbol ?? `#${d.signal_id}`}
                  </td>
                  <td
                    className={`py-2 pr-4 font-semibold ${
                      d.decision === "APPROVED" ? "text-positive" : "text-negative"
                    }`}
                  >
                    {d.decision}
                  </td>
                  <td className="py-2 pr-4 text-gray-400">{d.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
