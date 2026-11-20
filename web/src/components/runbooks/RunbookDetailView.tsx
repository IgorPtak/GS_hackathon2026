import type { Runbook } from "../../api/types";
import { RunbookSource } from "./RunbookSource";
import { StepBody } from "./StepBody";

/** Read-only runbook: original source next to its normalized steps. */
export function RunbookDetailView({ runbook }: { runbook: Runbook }) {
  return (
    <div>
      <h3 className="font-semibold">{runbook.title}</h3>
      <p className="mb-3 text-xs text-slate-500">
        {runbook.format} · normalized by {runbook.normalized_by}
        {runbook.llm_model ? ` (${runbook.llm_model})` : ""} · v{runbook.version}
      </p>
      <div className="grid gap-3 lg:grid-cols-2">
        <RunbookSource source={runbook.source} format={runbook.format} />
        {runbook.steps.length === 0 ? (
          <p className="text-sm text-slate-500">This runbook has no steps</p>
        ) : (
          <ol className="space-y-2">
            {runbook.steps.map((step) => (
              <li key={step.index} className="rounded border border-slate-200 p-3">
                <StepBody step={step}>
                  {step.approval === "required" ? (
                    <span className="rounded bg-amber-100 px-1.5 text-xs leading-5 text-amber-800">
                      requires approval
                    </span>
                  ) : null}
                  {step.is_automatic ? (
                    <span className="text-xs text-slate-500">automatic</span>
                  ) : null}
                </StepBody>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
