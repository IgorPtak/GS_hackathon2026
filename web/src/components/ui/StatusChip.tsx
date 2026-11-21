import type { ReactNode } from "react";

import { cx } from "../../lib/cx";
import { Icon, type IconName } from "./icons";

export type ChipTone = "neutral" | "success" | "warning" | "critical" | "info";

const TONES: Record<ChipTone, string> = {
  neutral: "bg-fill text-ink-2",
  success: "bg-success/15 text-success-ink",
  warning: "bg-warning/20 text-warning-ink",
  critical: "bg-critical/12 text-critical-ink",
  info: "bg-accent/12 text-accent-ink",
};

/** Small status word with an optional icon: "Delivered", "Waiting for approval", "0 lost". */
export function StatusChip({
  tone = "neutral",
  icon,
  children,
}: {
  tone?: ChipTone;
  icon?: IconName;
  children: ReactNode;
}) {
  return (
    <span
      className={cx(
        "inline-flex h-6 items-center gap-1 rounded-full px-2.5 text-caption font-medium whitespace-nowrap",
        TONES[tone],
      )}
    >
      {icon ? <Icon name={icon} size={13} strokeWidth={2.2} /> : null}
      {children}
    </span>
  );
}
