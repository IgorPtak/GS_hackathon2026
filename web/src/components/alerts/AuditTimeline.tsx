import type { AuditEntry } from "../../api/types";
import { formatDateTime } from "./alertFormat";

const OUTCOME_CLASSES: Record<AuditEntry["outcome"], string> = {
  ok: "bg-green-500",
  error: "bg-red-500",
  pending: "bg-amber-400",
};

function verbLabel(verb: string): string {
  const text = verb.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Chronological audit entries of one alert. */
export function AuditTimeline({ entries }: { entries: readonly AuditEntry[] }) {
  if (entries.length === 0) return <p className="text-sm text-slate-500">No audit entries yet</p>;
  return (
    <ol className="space-y-2">
      {entries.map((entry) => (
        <li key={entry.id} className="flex gap-2 text-sm">
          <span
            aria-hidden
            className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${OUTCOME_CLASSES[entry.outcome]}`}
          />
          <div className="min-w-0">
            <p>
              <span className="font-medium">{verbLabel(entry.verb)}</span>
              <span className="text-slate-600">
                {" "}
                by {entry.actor.display_name ?? entry.actor.id}
              </span>
              {entry.outcome !== "ok" ? (
                <span className="text-slate-600"> ({entry.outcome})</span>
              ) : null}
            </p>
            <p className="text-xs text-slate-500">{formatDateTime(entry.at)}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
