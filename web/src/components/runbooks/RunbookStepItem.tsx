import type { ActionRun, ApprovalRequest, RenderedRunbookStep } from "../../api/types";
import { ActionRunStatusBadge } from "./ActionRunStatusBadge";
import { StepBody } from "./StepBody";

interface RunbookStepItemProps {
  step: RenderedRunbookStep;
  run: ActionRun | null;
  approval: ApprovalRequest | null;
  isBusy: boolean;
  onRun: () => void;
}

/** One rendered step with its latest action run, approval code and (for manual steps) a Run button. */
export function RunbookStepItem({ step, run, approval, isBusy, onRun }: RunbookStepItemProps) {
  const isRunnable = step.kind !== "text" && !step.is_automatic && step.action !== null;
  const isActive = run?.status === "running" || run?.status === "pending_approval";
  const missing = step.missing_fields ?? [];
  const result = run?.result ? JSON.stringify(run.result) : null;
  return (
    <li className="rounded border border-slate-200 p-3">
      <StepBody step={step}>
        {step.requires_approval ? (
          <span className="rounded bg-amber-100 px-1.5 text-xs leading-5 text-amber-800">
            requires approval
          </span>
        ) : null}
        {step.is_automatic ? <span className="text-xs text-slate-500">automatic</span> : null}
        {run ? <ActionRunStatusBadge status={run.status} /> : null}
      </StepBody>
      {missing.length > 0 ? (
        <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">
          Missing values: {missing.join(", ")}
        </p>
      ) : null}
      {run?.status === "pending_approval" && approval ? (
        <p className="mt-2 text-xs text-amber-800">
          Waiting for approval. Reply{" "}
          <span className="font-mono font-semibold">APPROVE {approval.approval_code}</span>
        </p>
      ) : null}
      {run?.error ? <p className="mt-2 text-xs break-words text-red-700">{run.error}</p> : null}
      {result ? (
        <p className="mt-2 font-mono text-xs break-words text-slate-600">{result}</p>
      ) : null}
      {isRunnable ? (
        <button
          type="button"
          disabled={isBusy || isActive}
          onClick={onRun}
          className="mt-2 rounded bg-slate-800 px-3 py-1 text-sm text-white disabled:opacity-40"
        >
          {isBusy ? "Starting..." : run ? "Run again" : "Run"}
        </button>
      ) : null}
    </li>
  );
}
