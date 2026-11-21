import { useLayoutEffect, useRef, useState, type FocusEvent, type ReactNode } from "react";

const GAP = 10;
/** Keeps the bubble this far from the window edges. */
const EDGE = 8;

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
 * Small label on hover or keyboard focus (not after a mouse click). The bubble is a manual
 * popover, so it lives in the top layer: a transformed or scrolling ancestor (page transitions,
 * the rail) can neither move it nor clip it, and it never adds a scrollbar. It is clamped to the
 * window. The trigger keeps its own accessible name; the bubble is aria-hidden.
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
  const bubble = useRef<HTMLSpanElement>(null);
  const [position, setPosition] = useState<Position | null>(null);

  useLayoutEffect(() => {
    const element = bubble.current;
    if (!element || !position) return;
    if (!element.matches(":popover-open")) element.showPopover();
    // Nudge back inside the window when the label would run off an edge.
    const rect = element.getBoundingClientRect();
    const shift =
      rect.left < EDGE
        ? EDGE - rect.left
        : rect.right > window.innerWidth - EDGE
          ? window.innerWidth - EDGE - rect.right
          : 0;
    element.style.translate = shift === 0 ? "" : `${String(shift)}px 0`;
  }, [position]);

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
          ref={bubble}
          popover="manual"
          aria-hidden="true"
          style={{ left: position.left, top: position.top, transform: position.transform }}
          className="pointer-events-none fixed inset-auto m-0 overflow-visible rounded-md border-0 bg-ink px-2 py-0.5 text-caption font-medium whitespace-nowrap text-window shadow-tile"
        >
          {label}
        </span>
      ) : null}
    </span>
  );
}
