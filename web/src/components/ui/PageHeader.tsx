import type { ReactNode } from "react";

/** Page title (28/600), muted context after it, and right-aligned actions. */
export function PageHeader({
  title,
  context,
  actions,
}: {
  title: string;
  context?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex min-h-[72px] flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b border-hairline px-8 py-4 max-sm:px-5">
      <h1 className="flex flex-wrap items-baseline gap-x-3 text-page font-semibold tracking-tight">
        {title}
        {context ? (
          <span className="text-row font-normal tracking-normal text-ink-2">
            <span aria-hidden="true">• </span>
            {context}
          </span>
        ) : null}
      </h1>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}
