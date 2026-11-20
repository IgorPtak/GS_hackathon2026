import { useEffect, useRef } from "react";

/** `×N` duplicate counter; bumps once when the count grows (skipped for reduced motion). */
export function CountBadge({ count }: { count: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const previous = useRef(count);

  useEffect(() => {
    const element = ref.current;
    const isReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (element && count > previous.current && !isReduced) {
      element.animate(
        [{ transform: "scale(1)" }, { transform: "scale(1.25)" }, { transform: "scale(1)" }],
        { duration: 220, easing: "ease-out" },
      );
    }
    previous.current = count;
  }, [count]);

  return (
    <span
      ref={ref}
      className="num inline-flex h-5 items-center rounded-full bg-fill px-2 text-caption font-semibold text-ink-2"
    >
      <span aria-hidden="true">×{count}</span>
      <span className="sr-only">{count} occurrences</span>
    </span>
  );
}
