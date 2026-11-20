import { useMemo } from "react";

import type { ConditionLeaf } from "../../api/types";
import { ConditionRow } from "./ConditionRow";
import { parseWhenFromRuleYaml, replaceWhenInRuleYaml } from "./conditionYaml";

interface RuleConditionFormProps {
  readonly yaml: string;
  readonly onChange: (nextYaml: string) => void;
}

const NEW_LEAF: ConditionLeaf = { field: "", op: "eq", value: "" };

/** Form for simple conditions (one leaf or a flat `all`); rewrites only the `when:` block. */
export function RuleConditionForm({ yaml, onChange }: RuleConditionFormProps) {
  const parsed = useMemo(() => parseWhenFromRuleYaml(yaml), [yaml]);

  if (parsed.kind === "complex") {
    return (
      <section aria-label="Condition" className="rounded border border-slate-200 bg-white p-3">
        <p className="text-sm text-slate-600">
          This condition is too complex for the form — edit it in YAML.
        </p>
      </section>
    );
  }

  const { leaves } = parsed;
  // Once a second row exists the block must be an `all`, so the single-leaf shape is dropped.
  const write = (next: readonly ConditionLeaf[]) => {
    onChange(replaceWhenInRuleYaml(yaml, next, parsed.isSingleLeaf && next.length === 1));
  };

  return (
    <section
      aria-label="Condition"
      className="space-y-2 rounded border border-slate-200 bg-white p-3"
    >
      <h4 className="text-sm font-semibold">Condition (all of)</h4>
      <ul className="space-y-2">
        {leaves.map((leaf, index) => (
          <ConditionRow
            // Rows have no identity beyond position; removal remounts later rows, which is fine.
            key={`${String(index)}-${String(leaves.length)}`}
            leaf={leaf}
            index={index}
            canRemove={leaves.length > 1}
            onChange={(next) => {
              write(leaves.map((item, i) => (i === index ? next : item)));
            }}
            onRemove={() => {
              write(leaves.filter((_, i) => i !== index));
            }}
          />
        ))}
      </ul>
      <button
        type="button"
        onClick={() => {
          write([...leaves, NEW_LEAF]);
        }}
        className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
      >
        Add condition
      </button>
    </section>
  );
}
