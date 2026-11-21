import type { RunbookStep } from "../../api/types";
import { Card } from "../ui/Card";
import { RunbookStepRow } from "./RunbookStepRow";

/** Steps as a checklist card. */
export function RunbookStepList({ steps }: { steps: readonly RunbookStep[] }) {
  if (steps.length === 0) {
    return <p className="text-body text-ink-2">This runbook has no steps yet.</p>;
  }
  return (
    <Card isPadded={false}>
      <ol aria-label="Runbook steps" className="divide-y divide-hairline">
        {steps.map((step, i) => (
          <RunbookStepRow key={step.index} step={step} position={i + 1} />
        ))}
      </ol>
    </Card>
  );
}
