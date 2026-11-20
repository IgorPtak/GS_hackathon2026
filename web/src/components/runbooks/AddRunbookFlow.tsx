import { useState } from "react";

import type { Runbook } from "../../api/types";
import { useToast } from "../ui/toastContext";
import { AddRunbookForm, type RunbookDraft } from "./AddRunbookForm";
import { AddRunbookReview, ReadingRunbook } from "./AddRunbookReview";
import { useAddRunbook } from "./useAddRunbook";

interface AddRunbookFlowProps {
  readonly teamId: string | null;
  readonly existingIds: readonly string[];
  readonly onSaved: (runbook: Runbook) => void;
}

const EMPTY_DRAFT: RunbookDraft = { title: "", source: "", format: "text", fileName: null };

/** Add a runbook: paste or pick a file, review the steps Beacon found, save. */
export function AddRunbookFlow({ teamId, existingIds, onSaved }: AddRunbookFlowProps) {
  const [draft, setDraft] = useState<RunbookDraft>(EMPTY_DRAFT);
  const add = useAddRunbook(teamId);
  const toast = useToast();

  if (add.isReading || add.isSaving) return <ReadingRunbook />;
  if (add.preview) {
    return (
      <AddRunbookReview
        preview={add.preview}
        title={draft.title}
        existingIds={existingIds}
        isSaving={add.isSaving}
        error={add.saveError}
        onBack={add.reset}
        onSave={(id) => {
          void add.save(id, draft.title.trim()).then((saved) => {
            if (!saved) return;
            toast.show("Runbook saved");
            onSaved(saved);
          });
        }}
      />
    );
  }
  return (
    <AddRunbookForm
      draft={draft}
      isReading={false}
      error={add.readError}
      onChange={setDraft}
      onRead={() => {
        if (draft.title.trim() === "") {
          const firstLine = draft.source.trim().split("\n")[0] ?? "";
          setDraft({
            ...draft,
            title: firstLine
              .replace(/^#+\s*/, "")
              .slice(0, 60)
              .trim(),
          });
        }
        void add.read(draft.format, draft.source);
      }}
    />
  );
}
