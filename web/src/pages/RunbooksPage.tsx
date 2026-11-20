import { useState } from "react";

import { AddRunbookFlow } from "../components/runbooks/AddRunbookFlow";
import { RunbookDetailView } from "../components/runbooks/RunbookDetailView";
import { RunbookList } from "../components/runbooks/RunbookList";
import { useRunbooks } from "../components/runbooks/useRunbooks";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Skeleton } from "../components/ui/Skeleton";

type View =
  | { readonly name: "list" }
  | { readonly name: "add" }
  | { readonly name: "detail"; readonly id: string; readonly isNew: boolean };

/** Runbooks: cards, one runbook's step checklist, and the add flow. */
export function RunbooksPage({ teamId }: { readonly teamId: string | null }) {
  const [view, setView] = useState<View>({ name: "list" });
  const state = useRunbooks(view.name === "detail" ? view.id : null);

  function showList() {
    setView({ name: "list" });
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex min-h-9 items-center justify-between gap-3">
        {view.name === "list" ? (
          <>
            <p className="text-body text-ink-2">
              {state.summaries.length > 0
                ? `${String(state.summaries.length)} ${state.summaries.length === 1 ? "runbook" : "runbooks"}`
                : "Step-by-step help for responders"}
            </p>
            <Button
              variant="primary"
              icon="plus"
              onClick={() => {
                setView({ name: "add" });
              }}
            >
              Add a runbook
            </Button>
          </>
        ) : (
          <Button variant="ghost" onClick={showList}>
            ← All runbooks
          </Button>
        )}
      </div>
      {view.name === "list" ? (
        <RunbookList
          items={state.summaries}
          isLoading={state.isListLoading}
          error={state.listError}
          onOpen={(id) => {
            setView({ name: "detail", id, isNew: false });
          }}
          onAdd={() => {
            setView({ name: "add" });
          }}
        />
      ) : null}
      {view.name === "add" ? (
        <AddRunbookFlow
          teamId={teamId}
          existingIds={state.summaries.map((s) => s.id)}
          onSaved={(saved) => {
            state.reload();
            setView({ name: "detail", id: saved.id, isNew: true });
          }}
        />
      ) : null}
      {view.name === "detail" ? (
        <>
          {state.isRunbookLoading ? <Skeleton className="h-64 rounded-card" /> : null}
          {state.runbookError ? (
            <Card>
              <p role="alert" className="text-body text-critical-ink">
                Beacon could not open this runbook ({state.runbookError}). Go back and try again.
              </p>
            </Card>
          ) : null}
          {state.runbook ? <RunbookDetailView runbook={state.runbook} isNew={view.isNew} /> : null}
        </>
      ) : null}
    </div>
  );
}
