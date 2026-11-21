import type { ReactNode } from "react";

import { cx } from "../../lib/cx";
import { Icon, type IconName } from "../ui/icons";

interface HomeTileProps {
  readonly icon: IconName;
  readonly title: string;
  readonly value?: string;
  readonly caption?: string;
  readonly onOpen: () => void;
  readonly className?: string;
  readonly children?: ReactNode;
}

/** One clickable summary card on the home page: icon, big value, caption, optional body. */
export function HomeTile({
  icon,
  title,
  value,
  caption,
  onOpen,
  className,
  children,
}: HomeTileProps) {
  return (
    <button
      type="button"
      onClick={onOpen}
      className={cx(
        "group flex flex-col gap-4 rounded-card border border-hairline bg-card p-6 text-left shadow-card transition-[box-shadow,translate] duration-300 hover:-translate-y-0.5 hover:shadow-tile active:translate-y-0",
        className,
      )}
    >
      <span className="flex items-center justify-between">
        <span className="flex items-center gap-2.5 text-body font-medium text-ink-2">
          <span className="flex size-8 items-center justify-center rounded-full bg-fill text-ink">
            <Icon name={icon} size={17} />
          </span>
          {title}
        </span>
        <span className="text-ink-3 transition-[translate,color] duration-300 group-hover:translate-x-0.5 group-hover:text-ink">
          <Icon name="chevronRight" size={18} />
        </span>
      </span>
      {value !== undefined ? (
        <span className="flex items-baseline gap-2">
          {value === "" ? (
            <span className="h-10 w-14 animate-pulse rounded-tile bg-fill" aria-label="Loading" />
          ) : (
            <span className="num text-hero font-semibold tracking-tight">{value}</span>
          )}
          {caption ? <span className="text-body text-ink-2">{caption}</span> : null}
        </span>
      ) : null}
      {children}
    </button>
  );
}
