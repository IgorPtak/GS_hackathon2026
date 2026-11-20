import type { ReactNode } from "react";

import { cx } from "../../lib/cx";

const SIDES = {
  right: "left-full top-1/2 ml-3 -translate-y-1/2",
  top: "bottom-full left-1/2 mb-2 -translate-x-1/2",
  bottom: "top-full left-1/2 mt-2 -translate-x-1/2",
} as const;

/**
 * CSS-only tooltip shown on hover and keyboard focus. The trigger keeps its own accessible
 * name, so the bubble is aria-hidden and never the only source of a label.
 */
export function Tooltip({
  label,
  side = "right",
  children,
}: {
  label: string;
  side?: keyof typeof SIDES;
  children: ReactNode;
}) {
  return (
    <span className="group/tip relative inline-flex">
      {children}
      <span
        aria-hidden="true"
        className={cx(
          "pointer-events-none absolute z-50 rounded-lg bg-ink px-2.5 py-1 text-meta font-medium whitespace-nowrap text-window opacity-0 transition-opacity group-focus-within/tip:opacity-100 group-hover/tip:opacity-100",
          SIDES[side],
        )}
      >
        {label}
      </span>
    </span>
  );
}
