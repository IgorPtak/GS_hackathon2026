import { useState } from "react";

import type { ApprovalRequest } from "../../api/types";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Skeleton } from "../ui/Skeleton";
import { useToast } from "../ui/toastContext";
import { ApprovalCard } from "./ApprovalCard";
import { RecentDecisionsList } from "./RecentDecisionsList";
import { useApprovalDecision, type DecisionKind } from "./useApprovalDecision";
import { useLingeringRequests, type Outcome } from "./useLingeringRequests";

interface ApprovalQueueProps {
  readonly team: string;
  readonly items: readonly ApprovalRequest[];
  readonly decided: readonly ApprovalRequest[];
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly getAlertTitle: (alertId: string) => string;
  readonly getRunbookTitle: (runbookId: string) => string;
  readonly onApply: (request: ApprovalRequest) => void;
  readonly onReload: () => void;
  readonly onOpenAlert: (alertId: string) => void;
}

/** Pending runbook approvals followed by the collapsible recent decisions history. */
export function ApprovalQueue({
  team,
  items,
  decided,
  isLoading,
  error,
  getAlertTitle,
  getRunbookTitle,
  onApply,
  onReload,
  onOpenAlert,
}: ApprovalQueueProps) {
  const toast = useToast();
  const decision = useApprovalDecision(team, onApply);
  // Decisions made here are known right away; ones from the phone come with the decided list.
  const [localOutcomes] = useState(() => new Map<string, Outcome>());
  const outcomeOf = (id: string): Outcome => {
    const local = localOutcomes.get(id);
    if (local) return local;
    const done = decided.find((request) => request.id === id);
    return done?.decision === "reject" ? "reject" : "approve";
  };
  const shown = useLingeringRequests(items, outcomeOf);

  async function handleDecide(id: string, kind: DecisionKind, comment: string) {
    localOutcomes.set(id, kind);
    const ok = await decision.decide(id, kind, comment);
    if (ok) {
      toast.show(
        kind === "approve" ? "Approved. The runbook carries on." : "Rejected. The step is skipped.",
        kind === "approve" ? "success" : "info",
      );
    } else {
      localOutcomes.delete(id);
    }
  }

  return (
    <section aria-labelledby="runbook-approvals-heading" className="space-y-4">
      {items.length > 0 || isLoading || error ? (
        <div className="flex items-center justify-between gap-3">
          <h2 id="runbook-approvals-heading" className="text-card-title font-semibold text-ink">
            Runbook requests
          </h2>
          {items.length > 0 ? (
            <span className="num text-meta font-medium text-ink-2">{items.length} waiting</span>
          ) : null}
        </div>
      ) : null}

      {isLoading ? (
        <Card className="space-y-3">
          <Skeleton className="h-5 w-72" />
          <Skeleton className="h-4 w-56" />
          <Skeleton className="h-9 w-full" />
        </Card>
      ) : null}

      {error ? (
        <Card className="flex flex-wrap items-center justify-between gap-3 border-critical/30 bg-critical/8">
          <p role="alert" className="text-body text-critical-ink">
            Could not load approvals ({error}).
          </p>
          <Button variant="secondary" onClick={onReload}>
            Retry
          </Button>
        </Card>
      ) : null}

      {shown.length > 0 ? (
        <ul className="flex flex-col">
          {shown.map(({ request, outcome, isFolding }) => (
            <ApprovalCard
              key={request.id}
              outcome={outcome}
              isFolding={isFolding}
              request={request}
              alertTitle={getAlertTitle(request.alert_id)}
              runbookTitle={getRunbookTitle(request.runbook_id)}
              busyKind={decision.busyId === request.id ? decision.busyKind : null}
              error={decision.errors[request.id] || null}
              onOpenAlert={onOpenAlert}
              onDecide={(kind, comment) => {
                void handleDecide(request.id, kind, comment);
              }}
            />
          ))}
        </ul>
      ) : null}

      <RecentDecisionsList items={decided} />
    </section>
  );
}
