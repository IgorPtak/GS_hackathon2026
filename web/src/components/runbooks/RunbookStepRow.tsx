import type { RunbookStep } from "../../api/types";
import { Icon } from "../ui/icons";
import { StatusChip } from "../ui/StatusChip";
import { plainStepText, stepIconName, stepKindLabel } from "./runbookFormat";

/** One step of a runbook: kind icon, plain text, action name, approval chip and how it runs. */
export function RunbookStepRow({ step, position }: { step: RunbookStep; position: number }) {
  const needsApproval = step.approval === "required";
  return (
    <li className="flex gap-4 px-5 py-4">
      <span
        title={stepKindLabel(step.kind)}
        className="flex size-9 shrink-0 items-center justify-center rounded-full bg-fill text-ink-2"
      >
        <Icon name={stepIconName(step.kind)} size={18} />
        <span className="sr-only">{stepKindLabel(step.kind)}</span>
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-body font-medium break-words whitespace-pre-wrap">
          <span className="num mr-2 text-ink-2">{position}.</span>
          {plainStepText(step.text)}
        </p>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-meta text-ink-2">
          {step.action ? <span className="font-mono">{step.action}</span> : null}
          <span>{step.is_automatic ? "Runs automatically" : "Manual"}</span>
          {step.run_if !== "always" ? (
            <span>
              {step.run_if === "previous_failed"
                ? "Only if the step before failed"
                : "Only if the step before worked"}
            </span>
          ) : null}
          {step.max_attempts > 1 ? <span>Up to {String(step.max_attempts)} tries</span> : null}
        </div>
      </div>
      {needsApproval ? (
        <span className="shrink-0 self-start">
          <StatusChip tone="warning" icon="approval">
            Needs approval
          </StatusChip>
        </span>
      ) : null}
    </li>
  );
}
