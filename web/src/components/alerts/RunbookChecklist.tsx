import type {
  ActionRun,
  ApprovalRequest,
  RenderedRunbook,
  RenderedRunbookStep,
} from "../../api/types";
import { cx } from "../../lib/cx";
import { Button } from "../ui/Button";
import { Icon } from "../ui/icons";
import { Spinner } from "../ui/Spinner";
import { StatusChip } from "../ui/StatusChip";
import { useStepRun } from "../runbooks/useStepRun";

interface RunbookChecklistProps {
  readonly runbook: RenderedRunbook;
  readonly team: string;
  readonly actionRuns: readonly ActionRun[];
  readonly approvals: readonly ApprovalRequest[];
  readonly onRunStarted: (run: ActionRun) => void;
}

/** The most recent run of a step: highest attempt, then newest. */
function latestRun(runs: readonly ActionRun[], step: RenderedRunbookStep): ActionRun | null {
  let best: ActionRun | null = null;
  for (const run of runs) {
    if (run.step_index !== step.index) continue;
    const isNewer =
      !best ||
      run.attempt > best.attempt ||
      (run.attempt === best.attempt && Date.parse(run.updated_at) >= Date.parse(best.updated_at));
    if (isNewer) best = run;
  }
  return best;
}

function StepCheck({ run }: { run: ActionRun | null }) {
  if (run?.status === "running") return <Spinner size={16} label="In progress" />;
  const isDone = run?.status === "succeeded";
  const isFailed = run?.status === "failed" || run?.status === "rejected";
  return (
    <span
      className={cx(
        "flex size-5 items-center justify-center rounded-full border-[1.5px]",
        isDone && "border-success bg-success text-white",
        isFailed && "border-critical bg-critical text-white",
        !isDone && !isFailed && "border-ink-3",
      )}
    >
      {isDone ? <Icon name="check" size={12} strokeWidth={3} /> : null}
      {isFailed ? <Icon name="cross" size={11} strokeWidth={3} /> : null}
    </span>
  );
}

/** Runbook steps as a checklist: ticks as runs finish, with a Run button for manual steps. */
export function RunbookChecklist({
  runbook,
  team,
  actionRuns,
  approvals,
  onRunStarted,
}: RunbookChecklistProps) {
  const { busyIndex, error, run } = useStepRun(runbook.alert_id, team, onRunStarted);
  if (runbook.steps.length === 0) {
    return <p className="text-meta text-ink-2">This runbook has no steps.</p>;
  }
  return (
    <div>
      {error ? (
        <p
          role="alert"
          className="mb-2 rounded-input bg-critical/12 px-3 py-2 text-meta text-critical-ink"
        >
          {error}
        </p>
      ) : null}
      <ul className="flex flex-col gap-1">
        {runbook.steps.map((step) => {
          const stepRun = latestRun(actionRuns, step);
          const approval = approvals.find(
            (a) => a.action_run_id === stepRun?.id && a.decision === null,
          );
          const isRunnable = step.kind !== "text" && !step.is_automatic && step.action !== null;
          const isActive = stepRun?.status === "running" || stepRun?.status === "pending_approval";
          const isDone = stepRun?.status === "succeeded";
          return (
            <li key={step.index} className="flex items-start gap-3 rounded-tile px-1 py-2">
              <span className="mt-0.5">
                <StepCheck run={stepRun} />
              </span>
              <div className="min-w-0 flex-1">
                <p className={cx("text-body", isDone ? "text-ink-2" : "text-ink")}>{step.text}</p>
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  {step.requires_approval ? (
                    <StatusChip tone="warning">Needs approval</StatusChip>
                  ) : null}
                  {step.is_automatic ? <StatusChip>Automatic</StatusChip> : null}
                  {stepRun?.status === "pending_approval" ? (
                    <StatusChip tone="warning" icon="clock">
                      Waiting for approval
                    </StatusChip>
                  ) : null}
                  {stepRun?.status === "failed" ? (
                    <StatusChip tone="critical">Failed</StatusChip>
                  ) : null}
                </div>
                {approval ? (
                  <p className="mt-1 text-meta text-ink-2">
                    To approve by message, reply{" "}
                    <span className="num font-medium text-ink">
                      APPROVE {approval.approval_code}
                    </span>
                  </p>
                ) : null}
                {(step.missing_fields ?? []).length > 0 ? (
                  <p className="mt-1 text-meta text-warning-ink">
                    Missing values: {(step.missing_fields ?? []).join(", ")}
                  </p>
                ) : null}
                {stepRun?.error ? (
                  <p className="mt-1 text-meta break-words text-critical-ink">{stepRun.error}</p>
                ) : null}
              </div>
              {isRunnable && !isActive ? (
                <Button
                  size="md"
                  isLoading={busyIndex === step.index}
                  disabled={isActive}
                  onClick={() => {
                    void run(step.index);
                  }}
                >
                  {stepRun ? "Run again" : "Run"}
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
