import type { RunbookStep } from "../../api/types";

interface RunbookStepPreviewProps {
  readonly steps: readonly RunbookStep[];
  readonly step: RunbookStep;
}

/** Current runbook steps with the proposed step inserted at its index (highlighted). */
export function RunbookStepPreview({ steps, step }: RunbookStepPreviewProps) {
  const position = Math.min(Math.max(step.index, 0), steps.length);
  const rows = [
    ...steps.slice(0, position).map((s) => ({ s, isNew: false })),
    { s: step, isNew: true },
    ...steps.slice(position).map((s) => ({ s, isNew: false })),
  ];
  return (
    <ol aria-label="Runbook preview" className="space-y-1 text-sm">
      {rows.map(({ s, isNew }, i) => (
        <li
          key={`${String(i)}-${isNew ? "new" : "old"}`}
          className={`flex gap-2 rounded px-2 py-1 ${isNew ? "bg-green-50 text-green-900" : "bg-slate-50 text-slate-700"}`}
        >
          <span className="w-6 shrink-0 text-right font-mono">{i + 1}.</span>
          <span className="min-w-0 break-words">
            <span className="mr-1 rounded bg-slate-200 px-1 text-xs">{s.kind}</span>
            {s.text}
            {s.action ? <span className="ml-1 font-mono text-xs">[{s.action}]</span> : null}
            {isNew ? <span className="ml-2 text-xs font-semibold">new</span> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}
