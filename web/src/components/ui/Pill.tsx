import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cx } from "../../lib/cx";

interface PillProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> {
  readonly isActive: boolean;
  readonly count?: number;
  readonly onToggle: () => void;
  readonly children: ReactNode;
}

/** Filter toggle with an optional live count; active reads as a raised tile. */
export function Pill({ isActive, count, onToggle, children, className, ...rest }: PillProps) {
  return (
    <button
      type="button"
      aria-pressed={isActive}
      onClick={onToggle}
      className={cx(
        "inline-flex h-9 shrink-0 items-center gap-2 rounded-full border px-3.5 text-body font-medium whitespace-nowrap transition-[background-color,color,border-color,box-shadow,scale] select-none active:scale-[0.97]",
        isActive
          ? "border-hairline bg-card text-ink shadow-tile"
          : "border-transparent bg-fill text-ink-2 hover:text-ink",
        className,
      )}
      {...rest}
    >
      {children}
      {count === undefined ? null : (
        <span className={cx("num text-meta", isActive ? "text-ink-2" : "text-ink-3")}>{count}</span>
      )}
    </button>
  );
}
