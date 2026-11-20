import type { Runbook } from "../../api/types";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Icon } from "../ui/icons";
import { Skeleton } from "../ui/Skeleton";
import { StatusChip } from "../ui/StatusChip";
import { formatLabel, slugifyTitle, stepCountLabel } from "./runbookFormat";
import { RunbookSource } from "./RunbookSource";
import { RunbookStepList } from "./RunbookStepList";

/** Shown while the AI reads the runbook (it can take a few seconds). */
export function ReadingRunbook() {
  return (
    <div role="status" className="space-y-4">
      <h2 className="text-card-title font-semibold">Reading your runbook…</h2>
      <p className="text-body text-ink-2">
        Beacon is splitting it into steps. This can take a few seconds.
      </p>
      <Card isPadded={false} className="space-y-0 divide-y divide-hairline">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="flex gap-4 px-5 py-4">
            <Skeleton className="size-9 shrink-0 rounded-full" />
            <Skeleton className="h-9 flex-1" />
          </div>
        ))}
      </Card>
    </div>
  );
}

interface AddRunbookReviewProps {
  readonly preview: Runbook;
  readonly title: string;
  readonly existingIds: readonly string[];
  readonly isSaving: boolean;
  readonly error: string | null;
  readonly onBack: () => void;
  readonly onSave: (id: string) => void;
}

/** "Beacon turned this into N steps": review the checklist, then save. */
export function AddRunbookReview({
  preview,
  title,
  existingIds,
  isSaving,
  error,
  onBack,
  onSave,
}: AddRunbookReviewProps) {
  const id = slugifyTitle(title);
  const isReplacing = existingIds.includes(id);
  const approvals = preview.steps.filter((s) => s.approval === "required").length;
  const isFallback = preview.normalized_by === "fallback";
  const { steps } = preview;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-card-title font-semibold">
          {isFallback ? "Ready to add" : `Beacon turned this into ${stepCountLabel(steps.length)}`}
        </h2>
        {preview.normalized_by === "llm" ? (
          <StatusChip tone="info" icon="sparkle">
            AI{preview.llm_model ? ` · ${preview.llm_model}` : ""}
          </StatusChip>
        ) : null}
      </div>
      {isFallback ? (
        <div className="flex gap-3 rounded-card bg-fill px-5 py-4 text-meta text-ink-2">
          <Icon name="sparkle" size={18} className="mt-0.5 shrink-0" />
          <p>
            Beacon reads free text with AI when you save, then shows you the steps it found. You can
            edit anything afterwards and save again.
          </p>
        </div>
      ) : (
        <p className="-mt-3 text-body text-ink-2">
          {approvals > 0
            ? `${String(approvals)} ${approvals === 1 ? "step needs" : "steps need"} a person to approve before it runs. Check the list, then save.`
            : "Check the list, then save."}
        </p>
      )}
      {isFallback ? (
        <Card>
          <RunbookSource source={preview.source} format={formatLabel(preview.format)} />
        </Card>
      ) : (
        <RunbookStepList steps={steps} />
      )}
      {isReplacing ? (
        <p className="text-meta text-ink-2">
          A runbook called “{title}” already exists. Saving adds a new version of it.
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-body text-critical-ink">
          {error}
        </p>
      ) : null}
      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={onBack}>
          Edit the text
        </Button>
        <Button
          variant="primary"
          size="lg"
          isLoading={isSaving}
          disabled={id === ""}
          onClick={() => {
            onSave(id);
          }}
        >
          {isFallback ? "Save and read it" : "Save runbook"}
        </Button>
      </div>
      {id === "" ? (
        <p className="-mt-3 text-right text-meta text-ink-2">Give the runbook a name to save it.</p>
      ) : null}
    </div>
  );
}
