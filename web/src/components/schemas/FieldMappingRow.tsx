import type { ConfigValidationError, FieldMappingSpec } from "../../api/types";
import { FieldErrors } from "./FieldErrors";
import { ValueMapTable } from "./ValueMapTable";
import { emptySpec, TIME_FORMATS, type FieldName } from "./schemaDraft";

interface FieldMappingRowProps {
  readonly name: FieldName;
  readonly spec: FieldMappingSpec | null;
  readonly paths: readonly string[];
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (spec: FieldMappingSpec | null) => void;
}

const LABELS: Record<FieldName, string> = {
  type: "Type",
  source: "Source",
  severity: "Severity",
  occurred_at: "Occurred at",
  entity: "Entity",
};

/** One normalized field: a dropdown of the sample's key paths, plus severity/time extras. */
export function FieldMappingRow({ name, spec, paths, errors, onChange }: FieldMappingRowProps) {
  const current = spec?.path ?? "";
  const options = current !== "" && !paths.includes(current) ? [current, ...paths] : paths;
  const base = spec ?? emptySpec();

  return (
    <div className="rounded border border-slate-200 bg-white p-2">
      <div className="flex flex-wrap items-center gap-2">
        <label htmlFor={`field-${name}`} className="w-24 shrink-0 text-sm font-medium">
          {LABELS[name]}
        </label>
        {spec?.const != null ? (
          <span className="text-sm">
            constant <code className="font-mono">{spec.const}</code>
          </span>
        ) : null}
        <select
          id={`field-${name}`}
          value={current}
          onChange={(e) => {
            onChange(e.target.value === "" ? null : { ...base, const: null, path: e.target.value });
          }}
          className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 font-mono text-sm"
        >
          <option value="">none</option>
          {options.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        {name === "occurred_at" && spec ? (
          <select
            aria-label="Time format"
            value={spec.format ?? ""}
            onChange={(e) => {
              const format = TIME_FORMATS.find((f) => f === e.target.value) ?? null;
              onChange({ ...spec, format });
            }}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            <option value="">format: auto</option>
            {TIME_FORMATS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
        ) : null}
      </div>
      {name === "severity" && spec ? (
        <ValueMapTable
          valueMap={spec.value_map ?? {}}
          onChange={(value_map) => {
            onChange({ ...spec, value_map });
          }}
        />
      ) : null}
      <FieldErrors errors={errors} />
    </div>
  );
}
