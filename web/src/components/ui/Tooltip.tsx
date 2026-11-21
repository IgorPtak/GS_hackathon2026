import { useRef, useState, type FocusEvent, type ReactNode } from "react";

const GAP = 10;

type Side = "right" | "top" | "bottom";

interface Position {
  readonly left: number;
  readonly top: number;
  readonly transform: string;
}

function place(rect: DOMRect, side: Side): Position {
  if (side === "top") {
    return {
      left: rect.left + rect.width / 2,
      top: rect.top - GAP,
      transform: "translate(-50%, -100%)",
    };
  }
  if (side === "bottom") {
    return {
      left: rect.left + rect.width / 2,
      top: rect.bottom + GAP,
      transform: "translateX(-50%)",
    };
  }
  return { left: rect.right + GAP, top: rect.top + rect.height / 2, transform: "translateY(-50%)" };
}

/**
 * Small label on hover or keyboard focus (not after a mouse click). It is positioned `fixed`
 * from the trigger, so scrolling containers such as the rail never clip it. The trigger keeps
 * its own accessible name; the bubble is aria-hidden.
 */
export function Tooltip({
  label,
  side = "right",
  children,
}: {
  label: string;
  side?: Side;
  children: ReactNode;
}) {
  const anchor = useRef<HTMLSpanElement>(null);
  const [position, setPosition] = useState<Position | null>(null);

  function show() {
    const rect = anchor.current?.getBoundingClientRect();
    if (rect) setPosition(place(rect, side));
  }
  function hide() {
    setPosition(null);
  }
  function showOnKeyboardFocus(event: FocusEvent) {
    if (event.target instanceof HTMLElement && event.target.matches(":focus-visible")) show();
  }

  return (
    <span
      ref={anchor}
      className="relative inline-flex"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={showOnKeyboardFocus}
      onBlur={hide}
      onClick={hide}
    >
      {children}
      {position ? (
        <span
          aria-hidden="true"
          style={{ left: position.left, top: position.top, transform: position.transform }}
          className="pointer-events-none fixed z-50 rounded-md bg-ink px-2 py-0.5 text-caption font-medium whitespace-nowrap text-window shadow-tile"
        >
          {label}
        </span>
      ) : null}
    </span>
  );
}
