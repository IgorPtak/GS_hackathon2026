import type { ConfigValidationError } from "../../api/types";
import { cx } from "../../lib/cx";
import { Icon } from "../ui/icons";
import { FieldErrors } from "./FieldErrors";

interface FingerprintPickerProps {
  readonly selected: readonly string[];
  readonly paths: readonly string[];
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (next: string[]) => void;
}

/** Chips for the key paths whose values identify a repeated problem ("Group repeats by"). */
export function FingerprintPicker({ selected, paths, errors, onChange }: FingerprintPickerProps) {
  const all = [...new Set([...selected, ...paths])];
  return (
    <fieldset>
      <legend className="text-body font-semibold">Group repeats by</legend>
      <p className="mt-0.5 mb-3 text-meta text-ink-2">
        Events with the same values in these fields count as one alert.
      </p>
      <div className="flex flex-wrap gap-2">
        {all.map((path) => {
          const isOn = selected.includes(path);
          return (
            <button
              key={path}
              type="button"
              aria-pressed={isOn}
              onClick={() => {
                onChange(isOn ? selected.filter((p) => p !== path) : [...selected, path]);
              }}
              className={cx(
                "inline-flex h-8 items-center gap-1.5 rounded-full px-3 font-mono text-meta transition-colors",
                isOn ? "bg-ink text-window" : "bg-fill text-ink-2 hover:text-ink",
              )}
            >
              {isOn ? <Icon name="check" size={13} strokeWidth={2.4} /> : null}
              {path}
            </button>
          );
        })}
      </div>
      <FieldErrors errors={errors} />
    </fieldset>
  );
}
