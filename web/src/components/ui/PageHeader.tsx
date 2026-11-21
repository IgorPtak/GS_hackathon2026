import type { ReactNode } from "react";

import { Icon } from "./icons";
import { Tooltip } from "./Tooltip";

interface PageHeaderProps {
  readonly title: string;
  readonly context?: string;
  readonly actions?: ReactNode;
  /** Shows a quiet back chevron before the title when the screen is inside a sub-view. */
  readonly onBack?: () => void;
  readonly backLabel?: string;
}

/** Title with muted context ("Inbox • 7 open"), an optional back chevron and right actions. */
export function PageHeader({
  title,
  context,
  actions,
  onBack,
  backLabel = "Back",
}: PageHeaderProps) {
  return (
    <header className="flex min-h-[88px] flex-wrap items-center justify-between gap-x-6 gap-y-3 px-10 pt-7 pb-5 max-sm:px-5">
      <div className="flex min-w-0 items-center gap-3">
        {onBack ? (
          <Tooltip label={backLabel}>
            <button
              type="button"
              onClick={onBack}
              aria-label={backLabel}
              className="-ml-2 flex size-9 shrink-0 items-center justify-center rounded-full text-ink-2 transition-colors hover:bg-fill hover:text-ink"
            >
              <Icon name="chevronLeft" size={20} />
            </button>
          </Tooltip>
        ) : null}
        <h1 className="flex min-w-0 flex-wrap items-baseline gap-x-3 text-page font-medium tracking-tight">
          <span className="truncate">{title}</span>
          {context ? (
            <span className="text-page font-normal tracking-tight text-ink-2">
              <span aria-hidden="true" className="mr-3 align-middle text-[20px] text-ink-3/50">
                •
              </span>
              {context}
            </span>
          ) : null}
        </h1>
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </header>
  );
}
