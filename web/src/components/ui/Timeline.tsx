import type { ReactNode } from "react";

/** Ordered list of steps; the connector line is drawn by each TimelineStep. */
export function Timeline({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ol aria-label={label} className="flex flex-col">
      {children}
    </ol>
  );
}
