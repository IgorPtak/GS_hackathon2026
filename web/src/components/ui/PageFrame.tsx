import type { ReactNode } from "react";

import { PageHeader } from "./PageHeader";

/**
 * One screen: the white header band and the scrolling panel below it.
 * `isLegacy` pins not-yet-restyled content to the light scheme; drop it once a screen is redone.
 */
export function PageFrame({
  title,
  context,
  actions,
  isLegacy = false,
  children,
}: {
  title: string;
  context?: string;
  actions?: ReactNode;
  isLegacy?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <PageHeader title={title} context={context} actions={actions} />
      <main
        className={`${isLegacy ? "legacy-light " : ""}min-h-0 flex-1 overflow-y-auto bg-panel p-8 max-sm:p-4`}
      >
        {children}
      </main>
    </div>
  );
}
