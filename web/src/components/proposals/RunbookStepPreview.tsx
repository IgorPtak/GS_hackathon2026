import type { RunbookStep } from "../../api/types";
import { cx } from "../../lib/cx";
import { StatusChip } from "../ui/StatusChip";
import { STEP_KIND_LABELS } from "./fixLabels";

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
    <ol
      aria-label="Runbook preview"
      className="space-y-1.5 rounded-tile border border-hairline bg-panel p-2.5 text-meta"
    >
      {rows.map(({ s, isNew }, i) => (
        <li
          key={`${String(i)}-${isNew ? "new" : "old"}`}
          className={cx(
            "flex items-baseline gap-2.5 rounded-input px-3 py-2",
            isNew ? "bg-success/12 text-success-ink" : "bg-card text-ink",
          )}
        >
          <span className="num w-5 shrink-0 text-right font-mono text-caption text-ink-3">
            {i + 1}.
          </span>
          <span className="min-w-0 flex-1 break-words">
            <span className="mr-2 text-caption font-medium text-ink-2">
              {STEP_KIND_LABELS[s.kind]}
            </span>
            <span>{s.text}</span>
            {s.action ? (
              <span className="ml-1.5 font-mono text-caption text-ink-2">{s.action}</span>
            ) : null}
          </span>
          {isNew ? <StatusChip tone="success">Added</StatusChip> : null}
        </li>
      ))}
    </ol>
  );
}
