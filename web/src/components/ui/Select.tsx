import type { SelectHTMLAttributes } from "react";

import { cx } from "../../lib/cx";
import { CONTROL_CLASS } from "./controlStyles";
import { Icon } from "./icons";

export interface SelectOption {
  readonly value: string;
  readonly label: string;
}

interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange" | "value"> {
  readonly options: readonly SelectOption[];
  readonly value: string;
  readonly onChange: (value: string) => void;
}

/** Native <select> with our chevron; keyboard and mobile pickers come for free. */
export function Select({ options, value, onChange, className, ...rest }: SelectProps) {
  return (
    <span className="relative block">
      <select
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className={cx(CONTROL_CLASS, "appearance-none pr-10", className)}
        {...rest}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <Icon
        name="chevron"
        size={16}
        className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-ink-2"
      />
    </span>
  );
}
