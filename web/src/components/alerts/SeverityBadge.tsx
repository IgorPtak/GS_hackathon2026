import type { Alert } from "../../api/types";
import { colorClasses } from "./alertFormat";

/** Severity label tinted with the alert's presentation color. */
export function SeverityBadge({ alert }: { alert: Pick<Alert, "color" | "severity"> }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-1.5 text-xs leading-5 font-medium ${colorClasses(alert).badge}`}
    >
      <span aria-hidden className={`h-2 w-2 rounded-full ${colorClasses(alert).dot}`} />
      {alert.severity}
    </span>
  );
}
