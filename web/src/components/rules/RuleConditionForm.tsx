import { useMemo } from "react";

import type { ConditionLeaf, ConfigValidationError } from "../../api/types";
import { Button } from "../ui/Button";
import { ConditionRow, type ConditionRowErrors } from "./ConditionRow";
import { parseWhenFromRuleYaml, replaceWhenInRuleYaml } from "./conditionYaml";
import { conditionErrors } from "./ruleErrors";

interface RuleConditionFormProps {
  readonly yaml: string;
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (nextYaml: string) => void;
}

const NEW_LEAF: ConditionLeaf = { field: "", op: "eq", value: "" };

/** Friendly rows for simple conditions (one leaf or a flat `all`); rewrites only `when:`. */
export function RuleConditionForm({ yaml, errors, onChange }: RuleConditionFormProps) {
  const parsed = useMemo(() => parseWhenFromRuleYaml(yaml), [yaml]);

  if (parsed.kind === "complex") {
    return (
      <p className="rounded-tile bg-fill px-4 py-3 text-body text-ink-2">
        This condition is too complex for the form. Open Advanced (YAML) below to edit it.
      </p>
    );
  }

  const { leaves } = parsed;
  // Once a second row exists the block must be an `all`, so the single-leaf shape is dropped.
  const write = (next: readonly ConditionLeaf[]) => {
    onChange(replaceWhenInRuleYaml(yaml, next, parsed.isSingleLeaf && next.length === 1));
  };
  const rowErrors: ConditionRowErrors[] = leaves.map((_, index) =>
    conditionErrors(errors, index, parsed.isSingleLeaf),
  );

  return (
    <section aria-label="Condition" className="space-y-4">
      <p className="text-body text-ink-2">
        {leaves.length > 1
          ? "The rule fires when all of these are true:"
          : "The rule fires when this is true:"}
      </p>
      <ul className="space-y-3">
        {leaves.map((leaf, index) => (
          <ConditionRow
            // Rows have no identity beyond position; removal remounts later rows, which is fine.
            key={`${String(index)}-${String(leaves.length)}`}
            leaf={leaf}
            index={index}
            canRemove={leaves.length > 1}
            errors={rowErrors[index] ?? {}}
            onChange={(next) => {
              write(leaves.map((item, i) => (i === index ? next : item)));
            }}
            onRemove={() => {
              write(leaves.filter((_, i) => i !== index));
            }}
          />
        ))}
      </ul>
      <Button
        icon="plus"
        onClick={() => {
          write([...leaves, NEW_LEAF]);
        }}
      >
        Add condition
      </Button>
    </section>
  );
}
