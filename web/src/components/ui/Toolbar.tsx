import type { ReactNode } from "react";

/** Row under the header: one primary pill, a divider, then filter pills. */
export function Toolbar({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      role="toolbar"
      aria-label={label}
      className="flex flex-wrap items-center gap-2 border-b border-hairline px-8 py-3 max-sm:px-5"
    >
      {children}
    </div>
  );
}

/** Hairline vertical divider between the primary action and the filters. */
export function ToolbarDivider() {
  return <div role="separator" aria-orientation="vertical" className="mx-1 h-5 w-px bg-hairline" />;
}
