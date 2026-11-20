import type { ConditionLeaf } from "../../api/types";
import { ConditionValueInput } from "./ConditionValueInput";
import { CONDITION_OPS } from "./conditionYaml";

interface ConditionRowProps {
  readonly leaf: ConditionLeaf;
  readonly index: number;
  readonly canRemove: boolean;
  readonly onChange: (leaf: ConditionLeaf) => void;
  readonly onRemove: () => void;
}

/** Keeps the value's shape valid for the new operator (list for `in`, boolean for `exists`). */
function valueForOp(op: ConditionLeaf["op"], value: unknown): unknown {
  if (op === "exists") return true;
  if (op === "in") {
    if (Array.isArray(value)) return value;
    return value === null || value === "" ? [] : [value];
  }
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

/** One editable condition: field, operator, value. */
export function ConditionRow({ leaf, index, canRemove, onChange, onRemove }: ConditionRowProps) {
  const label = `Condition ${String(index + 1)}`;
  return (
    <li className="flex flex-wrap items-center gap-2">
      <input
        aria-label={`${label} field`}
        className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 font-mono text-sm"
        placeholder="payload.field"
        value={leaf.field}
        onChange={(event) => {
          onChange({ ...leaf, field: event.target.value });
        }}
      />
      <select
        aria-label={`${label} operator`}
        className="rounded border border-slate-300 px-2 py-1 text-sm"
        value={leaf.op}
        onChange={(event) => {
          const op = event.target.value as ConditionLeaf["op"];
          onChange({ ...leaf, op, value: valueForOp(op, leaf.value) });
        }}
      >
        {CONDITION_OPS.map((op) => (
          <option key={op} value={op}>
            {op}
          </option>
        ))}
      </select>
      <ConditionValueInput
        key={leaf.op === "in" || leaf.op === "exists" ? leaf.op : "scalar"}
        op={leaf.op}
        value={leaf.value}
        label={label}
        onChange={(value) => {
          onChange({ ...leaf, value });
        }}
      />
      <button
        type="button"
        aria-label={`Remove ${label.toLowerCase()}`}
        disabled={!canRemove}
        onClick={onRemove}
        className="rounded border border-slate-300 px-2 py-1 text-sm disabled:opacity-40"
      >
        Remove
      </button>
    </li>
  );
}
