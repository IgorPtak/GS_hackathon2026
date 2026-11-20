import type { ConfigValidationError } from "../../api/types";
import { FieldErrors } from "./FieldErrors";

interface FingerprintPickerProps {
  readonly selected: readonly string[];
  readonly paths: readonly string[];
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (next: string[]) => void;
}

/** Multi-select of the key paths whose values identify a repeated problem. */
export function FingerprintPicker({ selected, paths, errors, onChange }: FingerprintPickerProps) {
  const all = [...new Set([...selected, ...paths])];
  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-medium">Fingerprint (same values = same alert group)</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {all.map((path) => (
          <label key={path} className="flex items-center gap-1 font-mono text-xs break-all">
            <input
              type="checkbox"
              checked={selected.includes(path)}
              onChange={(e) => {
                onChange(
                  e.target.checked ? [...selected, path] : selected.filter((p) => p !== path),
                );
              }}
            />
            {path}
          </label>
        ))}
      </div>
      <FieldErrors errors={errors} />
    </fieldset>
  );
}
