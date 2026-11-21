import type { Alert } from "../../api/types";
import { formatDateTime } from "./alertFormat";

function formatValue(value: unknown): string {
  if (typeof value === "string") return value;
  if (value === null || value === undefined) return "-";
  return JSON.stringify(value);
}

/** Metadata and listed fields of an alert as a definition list. */
export function AlertFields({ alert }: { alert: Alert }) {
  const rows: readonly (readonly [string, string])[] = [
    ["Rule", alert.rule_id],
    ["Source", alert.source_id],
    ["Team", alert.team],
    ["Fingerprint", alert.fingerprint],
    ["First seen", formatDateTime(alert.first_seen)],
    ["Last seen", formatDateTime(alert.last_seen)],
    ...(alert.acknowledged_by
      ? [
          [
            "Acknowledged by",
            alert.acknowledged_by.display_name ?? alert.acknowledged_by.id,
          ] as const,
        ]
      : []),
    ...(alert.resolved_by
      ? [["Resolved by", alert.resolved_by.display_name ?? alert.resolved_by.id] as const]
      : []),
    ...(alert.resolution_reason ? [["Resolution reason", alert.resolution_reason] as const] : []),
    ...(alert.fields ?? []).map((field) => [field.path, formatValue(field.value)] as const),
  ];
  return (
    <dl className="grid grid-cols-[minmax(0,9rem)_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-meta">
      {rows.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="break-words text-ink-2">{label}</dt>
          <dd className="break-words text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
