import { useMemo, useState } from "react";

import { ApprovalQueue } from "../components/approvals/ApprovalQueue";
import { useApprovalContextTitles } from "../components/approvals/useAlertTitles";
import { useApprovals } from "../components/approvals/useApprovals";
import { FixProposalReview } from "../components/proposals/FixProposalReview";
import { useFixProposals } from "../components/proposals/useFixProposals";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { useEventStream } from "../hooks/useEventStream";
import type { TabId } from "../lib/tabs";

interface ApprovalsPageProps {
  readonly teamId: string | null;
  readonly onNavigate?: (tab: TabId) => void;
}

function TeamApprovals({
  team,
  onNavigate,
}: {
  readonly team: string;
  readonly onNavigate?: (tab: TabId) => void;
}) {
  const [isShowingDecidedFixes, setIsShowingDecidedFixes] = useState(false);
  const approvals = useApprovals(team);
  const proposals = useFixProposals(team, isShowingDecidedFixes);

  const { apply: applyApproval, reload: reloadApprovals } = approvals;
  const { apply: applyProposal, reload: reloadProposals } = proposals;

  useEventStream(team, {
    "approval.requested": (event) => {
      applyApproval(event.approval_request);
    },
    "approval.decided": (event) => {
      applyApproval(event.approval_request);
    },
    "fix_proposal.updated": (event) => {
      applyProposal(event.fix_proposal);
    },
    onReconnect: () => {
      reloadApprovals();
      reloadProposals();
    },
  });

  const alertIds = useMemo(
    () => [
      ...approvals.items.map((item) => item.alert_id),
      ...proposals.items.map((item) => item.alert_id),
    ],
    [approvals.items, proposals.items],
  );
  const titles = useApprovalContextTitles(team, alertIds);

  const isLoading = approvals.isLoading && proposals.isLoading;
  const hasAnyPending =
    approvals.items.length > 0 || proposals.items.some((item) => item.status === "pending");
  const isAllClear = !isLoading && !approvals.error && !proposals.error && !hasAnyPending;

  function openAlert(alertId: string) {
    const params = new URLSearchParams(window.location.search);
    params.set("alert", alertId);
    if (onNavigate) {
      window.history.replaceState(null, "", `/inbox?${params.toString()}`);
      onNavigate("inbox");
      return;
    }
    window.history.pushState(null, "", `/inbox?${params.toString()}`);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      {isAllClear ? (
        <Card isPadded={false}>
          <EmptyState icon="approval" title="Nothing waiting for you">
            Approvals from runbooks and proposed fixes show up here.
          </EmptyState>
        </Card>
      ) : null}

      <ApprovalQueue
        team={team}
        items={approvals.items}
        decided={approvals.decided}
        isLoading={approvals.isLoading}
        error={approvals.error}
        getAlertTitle={titles.getAlertTitle}
        getRunbookTitle={titles.getRunbookTitle}
        onApply={applyApproval}
        onReload={reloadApprovals}
        onOpenAlert={openAlert}
      />

      <FixProposalReview
        team={team}
        items={proposals.items}
        isLoading={proposals.isLoading}
        error={proposals.error}
        isShowingDecided={isShowingDecidedFixes}
        onToggleDecided={() => {
          setIsShowingDecidedFixes((prev) => !prev);
        }}
        getAlertTitle={titles.getAlertTitle}
        onApply={applyProposal}
        onReload={reloadProposals}
        onOpenAlert={openAlert}
        isHidingEmpty={isAllClear}
      />
    </div>
  );
}

/** Pending runbook approvals, recent decisions and fix proposals for the active team. */
export function ApprovalsPage({ teamId, onNavigate }: ApprovalsPageProps) {
  if (teamId === null) {
    return (
      <Card isPadded={false}>
        <EmptyState icon="approval">Select a team to see its pending approvals.</EmptyState>
      </Card>
    );
  }
  return <TeamApprovals key={teamId} team={teamId} onNavigate={onNavigate} />;
}
