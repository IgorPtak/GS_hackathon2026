import type { ConfigValidationError, FieldMappingSpec } from "../../api/types";
import { Select } from "../ui/Select";
import { FieldErrors } from "./FieldErrors";
import { ValueMapTable } from "./ValueMapTable";
import { emptySpec, FIELD_LABELS, TIME_FORMATS, type FieldName } from "./schemaDraft";

interface MappingRowProps {
  readonly name: FieldName;
  readonly spec: FieldMappingSpec | null;
  readonly paths: readonly string[];
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (spec: FieldMappingSpec | null) => void;
}

/** One shared field: "Severity ← lvl", with the value translations and time format when relevant. */
export function MappingRow({ name, spec, paths, errors, onChange }: MappingRowProps) {
  const current = spec?.path ?? "";
  const known = current !== "" && !paths.includes(current) ? [current, ...paths] : paths;
  const base = spec ?? emptySpec();
  const isConstant = spec?.const != null;
  const options = [
    { value: "", label: isConstant ? `Always "${spec.const ?? ""}"` : "Not mapped" },
    ...known.map((p) => ({ value: p, label: p })),
  ];

  return (
    <div className="py-3.5">
      <div className="grid grid-cols-[7rem_1.25rem_1fr] items-center gap-2 max-sm:grid-cols-[1fr] max-sm:gap-1.5">
        <span className="text-body font-semibold">{FIELD_LABELS[name]}</span>
        <span aria-hidden="true" className="text-ink-2 max-sm:hidden">
          ←
        </span>
        <div className="flex flex-wrap items-center gap-2">
          <div className="max-w-sm min-w-40 flex-1">
            <Select
              aria-label={`${FIELD_LABELS[name]} comes from`}
              value={current}
              options={options}
              className="font-mono"
              onChange={(next) => {
                onChange(next === "" ? null : { ...base, const: null, path: next });
              }}
            />
          </div>
          {name === "occurred_at" && spec ? (
            <div className="w-40 shrink-0">
              <Select
                aria-label="Time format"
                value={spec.format ?? ""}
                options={[
                  { value: "", label: "Detect format" },
                  ...TIME_FORMATS.map((f) => ({ value: f, label: f })),
                ]}
                onChange={(next) => {
                  onChange({ ...spec, format: TIME_FORMATS.find((f) => f === next) ?? null });
                }}
              />
            </div>
          ) : null}
        </div>
      </div>
      {name === "severity" && spec ? (
        <div className="sm:ml-[8.25rem]">
          <ValueMapTable
            valueMap={spec.value_map ?? {}}
            onChange={(value_map) => {
              onChange({ ...spec, value_map });
            }}
          />
        </div>
      ) : null}
      <div className="sm:ml-[8.25rem]">
        <FieldErrors errors={errors} />
      </div>
    </div>
  );
}
