import type { ReactNode } from "react";

import { usePageBack } from "../../lib/backContext";
import { cx } from "../../lib/cx";
import { PageHeader } from "./PageHeader";

interface PageFrameProps {
  readonly title: string;
  readonly context?: string;
  readonly actions?: ReactNode;
  /** A row of pills under the title, on the white band (like the reference toolbar). */
  readonly toolbar?: ReactNode;
  readonly onBack?: () => void;
  readonly backLabel?: string;
  /** Narrow, centred reading column for forms and flows; lists use the full width. */
  readonly isNarrow?: boolean;
  readonly isLegacy?: boolean;
  /** The page lays out its own panes (each scrolls on its own); no padding, no outer scroll. */
  readonly isFlush?: boolean;
  readonly children: ReactNode;
}

/** One screen: white header band (title, toolbar) over the calm grey scrolling body. */
export function PageFrame({
  title,
  context,
  actions,
  toolbar,
  onBack,
  backLabel,
  isNarrow = false,
  isLegacy = false,
  isFlush = false,
  children,
}: PageFrameProps) {
  // A page's own sub-view back wins; otherwise offer the way back after an in-page jump.
  const pageBack = usePageBack();
  return (
    <div className="page-frame relative flex min-h-0 flex-1 flex-col">
      <div className="page-header relative z-10 border-b border-hairline bg-card">
        <PageHeader
          title={title}
          context={context}
          actions={actions}
          onBack={onBack ?? pageBack?.onBack}
          backLabel={onBack ? backLabel : (pageBack?.label ?? backLabel)}
        />
        {toolbar ? <div className="px-10 pb-5 max-sm:px-5">{toolbar}</div> : null}
      </div>
      {isFlush ? (
        <main className="flex min-h-0 flex-1">{children}</main>
      ) : (
        <main
          className={cx(
            "page-scroll min-h-0 flex-1 overflow-y-auto px-10 py-9 max-sm:px-4 max-sm:py-5",
            isLegacy && "legacy-light",
          )}
        >
          <div className={cx("mx-auto w-full", isNarrow ? "max-w-[880px]" : "max-w-[1280px]")}>
            {children}
          </div>
        </main>
      )}
    </div>
  );
}
