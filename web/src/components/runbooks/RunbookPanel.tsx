import type {
  ActionRun,
  ApprovalRequest,
  RenderedRunbook,
  RenderedRunbookStep,
} from "../../api/types";
import { RunbookSource } from "./RunbookSource";
import { RunbookStepItem } from "./RunbookStepItem";
import { useStepRun } from "./useStepRun";

interface RunbookPanelProps {
  runbook: RenderedRunbook | null;
  team: string;
  actionRuns: readonly ActionRun[];
  approvals: readonly ApprovalRequest[];
  onRunStarted: (run: ActionRun) => void;
}

/** The most recent run of a step: highest attempt, then newest. */
function latestRun(runs: readonly ActionRun[], step: RenderedRunbookStep): ActionRun | null {
  let best: ActionRun | null = null;
  for (const run of runs) {
    if (run.step_index !== step.index) continue;
    if (
      !best ||
      run.attempt > best.attempt ||
      (run.attempt === best.attempt && Date.parse(run.updated_at) >= Date.parse(best.updated_at))
    )
      best = run;
  }
  return best;
}

/** Runbook of one alert: original source next to the rendered steps with live run status. */
export function RunbookPanel({
  runbook,
  team,
  actionRuns,
  approvals,
  onRunStarted,
}: RunbookPanelProps) {
  const alertId = runbook?.alert_id ?? "";
  const { busyIndex, error, run } = useStepRun(alertId, team, onRunStarted);
  if (!runbook) return <p className="text-sm text-slate-500">No runbook for this alert</p>;
  return (
    <div>
      <p className="mb-2 text-sm font-medium">{runbook.title}</p>
      {error ? (
        <p role="alert" className="mb-2 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      ) : null}
      <div className="grid gap-3 lg:grid-cols-2">
        <RunbookSource source={runbook.source} format={runbook.format} />
        {runbook.steps.length === 0 ? (
          <p className="text-sm text-slate-500">This runbook has no steps</p>
        ) : (
          <ol className="space-y-2">
            {runbook.steps.map((step) => {
              const stepRun = latestRun(actionRuns, step);
              const approval =
                approvals.find(
                  (item) => item.action_run_id === stepRun?.id && item.decision === null,
                ) ?? null;
              return (
                <RunbookStepItem
                  key={step.index}
                  step={step}
                  run={stepRun}
                  approval={approval}
                  isBusy={busyIndex === step.index}
                  onRun={() => {
                    void run(step.index);
                  }}
                />
              );
            })}
          </ol>
        )}
      </div>
    </div>
  );
}
