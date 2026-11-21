import { useState } from "react";

import type { FixProposal } from "../../api/types";
import { useLingeringItems, type Outcome } from "../approvals/useLingeringItems";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Pill } from "../ui/Pill";
import { Skeleton } from "../ui/Skeleton";
import { useToast } from "../ui/toastContext";
import { FixProposalCard } from "./FixProposalCard";
import { useFixDecision, type FixDecisionKind } from "./useFixDecision";

interface FixProposalReviewProps {
  readonly team: string;
  readonly items: readonly FixProposal[];
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly isShowingDecided: boolean;
  readonly onToggleDecided: () => void;
  readonly getAlertTitle: (alertId: string) => string;
  readonly onApply: (proposal: FixProposal) => void;
  readonly onReload: () => void;
  readonly onOpenAlert: (alertId: string) => void;
  readonly isHidingEmpty?: boolean;
}

/** Fix proposals owned by one team with clean diffs and Accept / Reject actions. */
export function FixProposalReview({
  team,
  items,
  isLoading,
  error,
  isShowingDecided,
  onToggleDecided,
  getAlertTitle,
  onApply,
  onReload,
  onOpenAlert,
  isHidingEmpty = false,
}: FixProposalReviewProps) {
  const toast = useToast();
  const decision = useFixDecision(team, onApply);
  // Decided here: known right away. Decided elsewhere: the list only says it left, so it reads
  // as done without a verdict we cannot see; "approve" keeps the quiet, positive veil.
  const [localOutcomes] = useState(() => new Map<string, Outcome>());
  const shown = useLingeringItems(items, (id) => localOutcomes.get(id) ?? "approve");

  async function handleDecide(id: string, kind: FixDecisionKind, comment: string) {
    localOutcomes.set(id, kind === "accept" ? "approve" : "reject");
    const ok = await decision.decide(id, kind, comment);
    if (ok) {
      toast.show(
        kind === "accept" ? "Accepted. The change is live." : "Rejected. Nothing changes.",
        kind === "accept" ? "success" : "info",
      );
    } else {
      localOutcomes.delete(id);
    }
  }

  const isEmpty = !isLoading && !error && shown.length === 0;
  if (isEmpty && isHidingEmpty && !isShowingDecided) {
    return (
      <div className="flex justify-end">
        <Pill isActive={false} onToggle={onToggleDecided}>
          Show past fix proposals
        </Pill>
      </div>
    );
  }

  return (
    <section aria-labelledby="fix-proposals-heading" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          <h2 id="fix-proposals-heading" className="text-card-title font-semibold text-ink">
            Fix proposals
          </h2>
          {items.length > 0 ? (
            <span className="num text-meta font-medium text-ink-2">{items.length} shown</span>
          ) : null}
        </div>
        <Pill isActive={isShowingDecided} onToggle={onToggleDecided}>
          Show decided
        </Pill>
      </div>

      {isLoading ? (
        <Card className="space-y-3">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-24 w-full" />
        </Card>
      ) : null}

      {error ? (
        <Card className="flex flex-wrap items-center justify-between gap-3 border-critical/30 bg-critical/8">
          <p role="alert" className="text-body text-critical-ink">
            Could not load fix proposals ({error}).
          </p>
          <Button variant="secondary" onClick={onReload}>
            Retry
          </Button>
        </Card>
      ) : null}

      {isEmpty ? (
        <Card className="text-body text-ink-2">
          {isShowingDecided
            ? "No fix proposals have been submitted for this team yet."
            : "No pending fix proposals."}
        </Card>
      ) : null}

      {shown.length > 0 ? (
        <ul className="flex flex-col">
          {shown.map(({ item: proposal, outcome, isFolding }) => (
            <FixProposalCard
              key={proposal.id}
              outcome={outcome}
              isFolding={isFolding}
              proposal={proposal}
              alertTitle={getAlertTitle(proposal.alert_id)}
              busyKind={decision.busyId === proposal.id ? decision.busyKind : null}
              error={decision.errors[proposal.id] || null}
              onOpenAlert={onOpenAlert}
              onDecide={(kind, comment) => {
                void handleDecide(proposal.id, kind, comment);
              }}
            />
          ))}
        </ul>
      ) : null}
    </section>
  );
}
