import type { ReactNode } from "react";

/** Grey canvas with one big white window (radius 28, 16 px gutter). */
export function AppWindow({ children }: { children: ReactNode }) {
  return (
    <div className="h-dvh min-h-[480px] p-4 max-sm:p-2">
      <div className="flex h-full overflow-hidden rounded-window bg-window shadow-window max-sm:rounded-card">
        {children}
      </div>
    </div>
  );
}
