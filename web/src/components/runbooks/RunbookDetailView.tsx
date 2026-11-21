import type { Runbook } from "../../api/types";
import { Icon } from "../ui/icons";
import { StatusChip } from "../ui/StatusChip";
import { formatLabel, normalizedByLabel, stepCountLabel } from "./runbookFormat";
import { RunbookSource } from "./RunbookSource";
import { RunbookStepList } from "./RunbookStepList";

/** One runbook: title, how it was read, the step checklist, and the original under "Advanced". */
export function RunbookDetailView({
  runbook,
  isNew = false,
}: {
  runbook: Runbook;
  isNew?: boolean;
}) {
  return (
    <div className="space-y-5">
      {isNew ? <JustAddedNotice runbook={runbook} /> : null}
      <div>
        <h2 className="text-card-title font-semibold">{runbook.title}</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2 text-meta text-ink-2">
          <span>{stepCountLabel(runbook.steps.length)}</span>
          <span aria-hidden="true">·</span>
          <span>{formatLabel(runbook.format)}</span>
          <span aria-hidden="true">·</span>
          <StatusChip
            tone={runbook.normalized_by === "llm" ? "info" : "neutral"}
            icon={runbook.normalized_by === "llm" ? "sparkle" : undefined}
          >
            {normalizedByLabel(runbook.normalized_by)}
            {runbook.llm_model ? ` · ${runbook.llm_model}` : ""}
          </StatusChip>
        </div>
      </div>
      <RunbookStepList steps={runbook.steps} />
      <details className="group rounded-card border border-hairline bg-card px-6 py-4">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-body font-semibold">
          <Icon
            name="chevron"
            size={16}
            className="-rotate-90 transition-transform group-open:rotate-0"
          />
          Advanced
          <span className="text-meta font-normal text-ink-2">
            original text and version {runbook.version}
          </span>
        </summary>
        <div className="mt-4">
          <RunbookSource source={runbook.source} format={formatLabel(runbook.format)} />
        </div>
      </details>
    </div>
  );
}

function JustAddedNotice({ runbook }: { runbook: Runbook }) {
  const approvals = runbook.steps.filter((s) => s.approval === "required").length;
  const isFallback = runbook.normalized_by === "fallback";
  return (
    <div
      role="status"
      className={`flex gap-3 rounded-card px-5 py-4 text-body ${isFallback ? "bg-warning/20 text-warning-ink" : "bg-success/10 text-ink"}`}
    >
      <Icon name={isFallback ? "alert" : "check"} size={20} className="mt-0.5 shrink-0" />
      <p>
        {isFallback
          ? "Saved, but the AI helper was not available, so Beacon kept your text as one step. Open Advanced to see it, or save again later."
          : `Saved. Beacon turned this into ${stepCountLabel(runbook.steps.length)}.${approvals > 0 ? ` ${String(approvals)} ${approvals === 1 ? "needs" : "need"} approval before running.` : ""}`}
      </p>
    </div>
  );
}
