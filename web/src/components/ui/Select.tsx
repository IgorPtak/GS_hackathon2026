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

/**
 * Native <select> with our chevron. Where `appearance: base-select` is supported the picker is a
 * rounded card from index.css; elsewhere the OS picker shows. Keyboard and a11y stay native.
 */
export function Select({ options, value, onChange, className, ...rest }: SelectProps) {
  return (
    <span className="group/select relative block">
      <select
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className={cx(
          CONTROL_CLASS,
          "select-base appearance-none pr-10 transition-[background-color,border-color] hover:bg-hairline/60 focus-visible:border-accent",
          className,
        )}
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
        className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-ink-2 transition-transform duration-300 group-has-[select:open]/select:rotate-180"
      />
    </span>
  );
}
