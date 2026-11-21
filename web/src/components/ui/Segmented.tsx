import { useId, useLayoutEffect, useRef, useState } from "react";

import { cx } from "../../lib/cx";
import type { SelectOption } from "./Select";

interface SegmentedProps {
  readonly label: string;
  readonly options: readonly SelectOption[];
  readonly value: string;
  readonly onChange: (value: string) => void;
  readonly size?: "md" | "lg";
}

interface Thumb {
  readonly left: number;
  readonly width: number;
}

/**
 * Radio group styled as one grey capsule; arrow keys move the choice natively. A single raised
 * thumb glides to the chosen option instead of the highlight jumping.
 */
export function Segmented({ label, options, value, onChange, size = "md" }: SegmentedProps) {
  const name = useId();
  const box = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState<Thumb | null>(null);

  useLayoutEffect(() => {
    const element = box.current;
    if (!element) return;
    const measure = () => {
      const checked = element.querySelector<HTMLElement>(`[data-value="${CSS.escape(value)}"]`);
      setThumb(checked ? { left: checked.offsetLeft, width: checked.offsetWidth } : null);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, [value, options]);

  return (
    <div
      ref={box}
      role="radiogroup"
      aria-label={label}
      className="relative inline-flex max-w-full gap-0.5 overflow-x-auto rounded-full bg-fill p-0.5 [scrollbar-width:none]"
    >
      {thumb ? (
        <span
          aria-hidden="true"
          className="absolute top-0.5 bottom-0.5 left-0 rounded-full bg-card shadow-tile transition-[translate,width] duration-[380ms] ease-[var(--ease-spring)]"
          style={{ translate: `${String(thumb.left)}px 0`, width: thumb.width }}
        />
      ) : null}
      {options.map((option) => (
        <label key={option.value} data-value={option.value} className="relative">
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={option.value === value}
            onChange={() => {
              onChange(option.value);
            }}
            className="peer sr-only"
          />
          <span
            className={cx(
              "flex cursor-pointer items-center rounded-full font-medium whitespace-nowrap text-ink-2 transition-colors duration-300 select-none peer-checked:text-ink peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent hover:text-ink",
              size === "lg" ? "h-9 px-4 text-body" : "h-8 px-3.5 text-meta",
            )}
          >
            {option.label}
          </span>
        </label>
      ))}
    </div>
  );
}
