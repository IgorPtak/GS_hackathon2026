import type { AuditEntry } from "../../api/types";
import { formatDateTime } from "./alertFormat";

function verbLabel(verb: string): string {
  const text = verb.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Raw audit entries of one alert, for the Details disclosure. */
export function AuditTimeline({ entries }: { entries: readonly AuditEntry[] }) {
  if (entries.length === 0) return <p className="text-meta text-ink-2">No audit entries yet.</p>;
  return (
    <ol className="divide-y divide-hairline text-meta">
      {entries.map((entry) => (
        <li key={entry.id} className="flex flex-wrap justify-between gap-x-3 py-1.5">
          <span>
            <span className="font-medium text-ink">{verbLabel(entry.verb)}</span>
            <span className="text-ink-2"> by {entry.actor.display_name ?? entry.actor.id}</span>
            {entry.outcome !== "ok" ? (
              <span className="text-warning-ink"> ({entry.outcome})</span>
            ) : null}
          </span>
          <span className="num text-ink-2">{formatDateTime(entry.at)}</span>
        </li>
      ))}
    </ol>
  );
}
