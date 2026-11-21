import type { ConditionLeaf } from "../../api/types";
import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { Select } from "../ui/Select";
import { TextInput } from "../ui/TextInput";
import { ConditionValueInput } from "./ConditionValueInput";
import { CONDITION_OPS } from "./conditionYaml";
import { opLabel } from "./ruleLabels";

export interface ConditionRowErrors {
  readonly field?: string;
  readonly op?: string;
  readonly value?: string;
}

interface ConditionRowProps {
  readonly leaf: ConditionLeaf;
  readonly index: number;
  readonly canRemove: boolean;
  readonly errors: ConditionRowErrors;
  readonly onChange: (leaf: ConditionLeaf) => void;
  readonly onRemove: () => void;
}

const OP_OPTIONS = CONDITION_OPS.map((op) => ({ value: op, label: opLabel(op) }));

/** Keeps the value's shape valid for the new operator (list for `in`, boolean for `exists`). */
function valueForOp(op: ConditionLeaf["op"], value: unknown): unknown {
  if (op === "exists") return true;
  if (op === "severity_gte") {
    const known = ["debug", "info", "warning", "error", "critical"];
    return typeof value === "string" && known.includes(value.toLowerCase()) ? value : "warning";
  }
  if (op === "time_between") {
    return typeof value === "string" && /^\d{2}:\d{2}-\d{2}:\d{2}$/.test(value)
      ? value
      : "08:00-20:00";
  }
  if (op === "in") {
    if (Array.isArray(value)) return value;
    return value === null || value === "" ? [] : [value];
  }
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

/** One friendly row: Field, "is greater than", Value. */
export function ConditionRow({
  leaf,
  index,
  canRemove,
  errors,
  onChange,
  onRemove,
}: ConditionRowProps) {
  const number = String(index + 1);
  return (
    <li className="rounded-tile border border-hairline bg-panel p-4">
      <div className="grid items-start gap-4 lg:grid-cols-[1fr_14rem_1.4fr_auto]">
        <Field label="Field" error={errors.field}>
          {(control) => (
            <TextInput
              {...control}
              className="font-mono text-meta"
              placeholder="payload.notional"
              value={leaf.field}
              onChange={(event) => {
                onChange({ ...leaf, field: event.target.value });
              }}
            />
          )}
        </Field>
        <Field label="Is it…" error={errors.op}>
          {(control) => (
            <Select
              {...control}
              options={OP_OPTIONS}
              value={leaf.op}
              onChange={(value) => {
                const op = value as ConditionLeaf["op"];
                onChange({ ...leaf, op, value: valueForOp(op, leaf.value) });
              }}
            />
          )}
        </Field>
        <Field label="Value" error={errors.value}>
          {(control) => (
            <ConditionValueInput
              key={
                ["in", "exists", "severity_gte", "time_between"].includes(leaf.op)
                  ? leaf.op
                  : "scalar"
              }
              control={control}
              op={leaf.op}
              value={leaf.value}
              label={`Condition ${number}`}
              onChange={(value) => {
                onChange({ ...leaf, value });
              }}
            />
          )}
        </Field>
        <Button
          variant="ghost"
          className="lg:mt-6"
          aria-label={`Remove condition ${number}`}
          disabled={!canRemove}
          onClick={onRemove}
        >
          Remove
        </Button>
      </div>
    </li>
  );
}
