import type { SystemEvent } from "@/types/trading";

function levelClass(level: SystemEvent["level"]): string {
  if (level === "ERROR") return "text-negative";
  if (level === "WARNING") return "text-yellow-400";
  return "text-gray-400";
}

export default function SystemEventsList({ events }: { events: SystemEvent[] }) {
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-400">System Events</h2>
      {events.length === 0 ? (
        <p className="text-sm text-gray-400">No events yet.</p>
      ) : (
        <ul className="max-h-96 space-y-1 overflow-y-auto text-sm">
          {events.map((e) => (
            <li key={e.id} className="flex gap-3 border-t border-border py-1.5 first:border-t-0">
              <span className="whitespace-nowrap font-mono text-xs text-gray-500">
                {new Date(e.timestamp).toLocaleTimeString("en-IN")}
              </span>
              <span className={`whitespace-nowrap text-xs font-semibold ${levelClass(e.level)}`}>{e.level}</span>
              <span className="whitespace-nowrap text-xs text-gray-500">[{e.category}]</span>
              <span className="text-gray-300">{e.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
