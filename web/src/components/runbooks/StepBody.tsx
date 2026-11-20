import type { RenderedRunbookStep } from "../../api/types";

export type StepBodyData = Pick<
  RenderedRunbookStep,
  "index" | "kind" | "text" | "action" | "params" | "run_if" | "max_attempts"
>;

/** Kind, text, action id + params and run_if of one step; callers add badges and status as children. */
export function StepBody({ step, children }: { step: StepBodyData; children?: React.ReactNode }) {
  const params = Object.entries(step.params ?? {});
  return (
    <div className="min-w-0 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-slate-500">#{step.index + 1}</span>
        <span className="rounded bg-slate-100 px-1.5 text-xs leading-5 text-slate-700">
          {step.kind}
        </span>
        {children}
      </div>
      <p className="mt-1 break-words whitespace-pre-wrap">{step.text}</p>
      {step.action ? (
        <p className="mt-1 font-mono text-xs break-words text-slate-600">
          {step.action}
          {params.length > 0 ? ` (${params.map(([k, v]) => `${k}=${v}`).join(", ")})` : ""}
        </p>
      ) : null}
      <p className="mt-1 text-xs text-slate-500">
        {step.run_if !== "always" ? `run if ${step.run_if.replaceAll("_", " ")}` : null}
        {step.run_if !== "always" && step.max_attempts > 1 ? " · " : null}
        {step.max_attempts > 1 ? `up to ${String(step.max_attempts)} attempts` : null}
      </p>
    </div>
  );
}
