import type { RunbookSummary } from "../../api/types";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { Skeleton } from "../ui/Skeleton";
import { RunbookCard } from "./RunbookCard";

interface RunbookListProps {
  readonly items: readonly RunbookSummary[];
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly onOpen: (id: string) => void;
  readonly onAdd: () => void;
}

/** Runbooks as cards, with loading, error and empty states. */
export function RunbookList({ items, isLoading, error, onOpen, onAdd }: RunbookListProps) {
  if (isLoading) {
    return (
      <div aria-label="Loading runbooks" className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-32 rounded-card" />
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <Card>
        <p role="alert" className="text-body text-critical-ink">
          Beacon could not load runbooks ({error}). Check that the API is running, then reload.
        </p>
      </Card>
    );
  }
  if (items.length === 0) {
    return (
      <Card>
        <EmptyState
          icon="runbook"
          action={
            <Button variant="primary" icon="plus" onClick={onAdd}>
              Add a runbook
            </Button>
          }
        >
          No runbooks yet. Paste your team's instructions and Beacon turns them into steps.
        </EmptyState>
      </Card>
    );
  }
  return (
    <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <RunbookCard
          key={item.id}
          item={item}
          onOpen={() => {
            onOpen(item.id);
          }}
        />
      ))}
    </ul>
  );
}
