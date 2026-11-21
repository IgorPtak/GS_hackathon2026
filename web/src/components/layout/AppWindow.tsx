import type { ReactNode } from "react";

/** The app fills the viewport edge to edge: no floating window, no outer canvas gutter. */
export function AppWindow({ children }: { children: ReactNode }) {
  return <div className="flex h-dvh min-h-[480px] overflow-hidden bg-window">{children}</div>;
}
