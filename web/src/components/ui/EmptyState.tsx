import type { ReactNode } from "react";

import { Icon, type IconName } from "./icons";
import { Illustration } from "./Illustration";
import type { Scene } from "./illustrations";

interface EmptyStateProps {
  readonly icon: IconName;
  /** A painted scene instead of the icon, for the big, calm empty states. */
  readonly scene?: Scene;
  readonly title?: string;
  readonly children: ReactNode;
  readonly action?: ReactNode;
}

/** Picture or icon, one inviting sentence and one action. */
export function EmptyState({ icon, scene, title, children, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center gap-4 px-6 py-12 text-center">
      {scene ? (
        <Illustration
          scene={scene}
          fade="edges"
          className="mb-2 aspect-[16/10] w-full max-w-[420px]"
        />
      ) : (
        <span className="flex size-20 items-center justify-center rounded-full bg-fill text-ink-3">
          <Icon name={icon} size={36} />
        </span>
      )}
      {title ? <h2 className="text-card-title font-semibold tracking-tight">{title}</h2> : null}
      <p className="max-w-sm text-body text-ink-2">{children}</p>
      {action}
    </div>
  );
}
