import type { MouseEvent } from "react";

import { cx } from "../../lib/cx";
import { Icon, type IconName } from "./icons";
import { Tooltip } from "./Tooltip";

interface RailItemProps {
  readonly label: string;
  readonly icon: IconName;
  readonly href: string;
  readonly isActive: boolean;
  /** Red count badge; hidden at 0. */
  readonly badge?: number;
  readonly onSelect: () => void;
}

/** A rail link. The active one is a raised white tile; plain clicks navigate without reload. */
export function RailItem({ label, icon, href, isActive, badge = 0, onSelect }: RailItemProps) {
  function handleClick(event: MouseEvent<HTMLAnchorElement>) {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
    event.preventDefault();
    onSelect();
  }

  return (
    <Tooltip label={label}>
      <a
        href={href}
        onClick={handleClick}
        aria-current={isActive ? "page" : undefined}
        aria-label={badge > 0 ? `${label}, ${String(badge)} pending` : label}
        className={cx(
          "relative flex size-11 items-center justify-center rounded-tile border transition-[background-color,color,border-color,box-shadow,scale] duration-300 active:scale-95",
          isActive
            ? "border-hairline bg-card text-ink shadow-tile"
            : "border-transparent text-ink-2 hover:bg-fill hover:text-ink",
        )}
      >
        <Icon name={icon} size={22} />
        {badge > 0 ? (
          <span
            aria-hidden="true"
            className="num absolute -top-1 -right-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-critical px-1 text-[11px] leading-none font-semibold text-white ring-2 ring-window"
          >
            {badge > 99 ? "99+" : badge}
          </span>
        ) : null}
      </a>
    </Tooltip>
  );
}
