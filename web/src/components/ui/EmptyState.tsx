import type { ReactNode } from "react";

import { Icon, type IconName } from "./icons";

/** Icon, one inviting sentence and one action. */
export function EmptyState({
  icon,
  children,
  action,
}: {
  icon: IconName;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-4 px-6 py-14 text-center">
      <span className="flex size-12 items-center justify-center rounded-full bg-fill text-ink-2">
        <Icon name={icon} size={24} />
      </span>
      <p className="max-w-sm text-body text-ink-2">{children}</p>
      {action}
    </div>
  );
}
