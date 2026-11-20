import { useId } from "react";

import type { SelectOption } from "./Select";

interface SegmentedProps {
  readonly label: string;
  readonly options: readonly SelectOption[];
  readonly value: string;
  readonly onChange: (value: string) => void;
}

/** Radio group styled as one grey capsule; arrow keys move the choice natively. */
export function Segmented({ label, options, value, onChange }: SegmentedProps) {
  const name = useId();
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex gap-0.5 rounded-full bg-fill p-0.5"
    >
      {options.map((option) => (
        <label key={option.value} className="relative">
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
          <span className="flex h-8 cursor-pointer items-center rounded-full px-3.5 text-meta font-medium text-ink-2 transition-colors peer-checked:bg-card peer-checked:text-ink peer-checked:shadow-tile peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent">
            {option.label}
          </span>
        </label>
      ))}
    </div>
  );
}
