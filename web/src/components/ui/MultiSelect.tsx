import { cx } from "../../lib/cx";
import { Icon } from "./icons";
import type { SelectOption } from "./Select";

interface MultiSelectProps {
  readonly label: string;
  readonly options: readonly SelectOption[];
  readonly values: readonly string[];
  readonly onChange: (values: string[]) => void;
}

/** Every option is a toggle chip, so the whole choice is visible without opening a menu. */
export function MultiSelect({ label, options, values, onChange }: MultiSelectProps) {
  function toggle(value: string) {
    onChange(values.includes(value) ? values.filter((item) => item !== value) : [...values, value]);
  }

  return (
    <div role="group" aria-label={label} className="flex flex-wrap gap-2">
      {options.map((option) => {
        const isSelected = values.includes(option.value);
        return (
          <button
            key={option.value}
            type="button"
            aria-pressed={isSelected}
            onClick={() => {
              toggle(option.value);
            }}
            className={cx(
              "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-meta font-medium transition-colors",
              isSelected
                ? "border-transparent bg-ink text-window"
                : "border-transparent bg-fill text-ink-2 hover:text-ink",
            )}
          >
            {isSelected ? <Icon name="check" size={13} strokeWidth={2.4} /> : null}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
