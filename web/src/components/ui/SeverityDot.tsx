import type { Severity } from "../../api/types";
import { cx } from "../../lib/cx";

const DOT_COLORS: Record<Severity, string> = {
  critical: "bg-critical",
  error: "bg-error",
  warning: "bg-warning",
  info: "bg-info",
  debug: "bg-ink-3",
};

/** Coloured dot with a screen-reader label, so severity never relies on colour alone. */
export function SeverityDot({ severity }: { severity: Severity }) {
  return (
    <span className="inline-flex items-center">
      <span aria-hidden="true" className={cx("size-2.5 rounded-full", DOT_COLORS[severity])} />
      <span className="sr-only">{severity}</span>
    </span>
  );
}
