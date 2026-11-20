import type { ReactNode } from "react";

/** Narrow left navigation column: logo on top, items in the middle, controls at the bottom. */
export function Rail({
  logo,
  footer,
  children,
}: {
  logo: ReactNode;
  footer: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="flex min-h-0 w-[72px] shrink-0 flex-col items-center gap-5 overflow-y-auto border-r border-hairline py-5 max-sm:w-16">
      {logo}
      <nav aria-label="Sections" className="flex flex-col items-center gap-1">
        {children}
      </nav>
      <div className="mt-auto flex flex-col items-center gap-3">{footer}</div>
    </div>
  );
}

/** Hairline between rail groups. */
export function RailDivider() {
  return <div role="presentation" className="my-2 h-px w-6 bg-hairline" />;
}
