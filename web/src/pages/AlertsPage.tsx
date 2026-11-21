import { useCallback, useState } from "react";
import { flushSync } from "react-dom";

import type { Alert } from "../api/types";
import { AlertDetailPane } from "../components/alerts/AlertDetailPane";
import { AlertList } from "../components/alerts/AlertList";
import { InboxToolbar } from "../components/alerts/InboxToolbar";
import { LivePipelineCard } from "../components/alerts/LivePipelineCard";
import { useAlertCounts } from "../components/alerts/useAlertCounts";
import { useAlertDetail } from "../components/alerts/useAlertDetail";
import { useAlertFeed, type StatusFilter } from "../components/alerts/useAlertFeed";
import { useAlertTransition } from "../components/alerts/useAlertTransition";
import { useSendTestAlert } from "../components/alerts/useSendTestAlert";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { PageFrame } from "../components/ui/PageFrame";
import { ConnectionIndicator } from "../components/alerts/ConnectionIndicator";
import { useEventStream } from "../hooks/useEventStream";

/** Below this width the detail pane is a full-width drill-down (docs/ui-design.md "Rail"). */
const NARROW_QUERY = "(max-width: 1099px)";

/** Cross-fades list and detail with the View Transitions API when it is there and motion is OK. */
function changeWithTransition(change: () => void): void {
  const isNarrow = window.matchMedia(NARROW_QUERY).matches;
  const isReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (isNarrow && !isReduced && "startViewTransition" in document) {
    document.startViewTransition(() => {
      flushSync(change);
    });
  } else {
    change();
  }
}

/** Inbox body for one team; the single SSE connection fans out to the list, counts and detail. */
function TeamInbox({
  team,
  teamLabel,
  onOpenInsights,
}: {
  team: string;
  teamLabel: string;
  onOpenInsights: () => void;
}) {
  const [filter, setFilter] = useState<StatusFilter>("open");
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const feed = useAlertFeed(team, filter);
  const detail = useAlertDetail(selectedAlertId);
  const { counts, refresh: refreshCounts } = useAlertCounts(team);
  const testAlert = useSendTestAlert(team, teamLabel);
  const { applyAlert: applyToFeed, reload: reloadFeed } = feed;
  const {
    applyAlert: applyToDetail,
    applyAudit,
    applyDelivery,
    applyActionRun,
    applyApproval,
    reload: reloadDetail,
  } = detail;

  const applyEverywhere = useCallback(
    (alert: Alert, isForced = false) => {
      applyToFeed(alert, isForced);
      applyToDetail(alert, isForced);
      refreshCounts();
    },
    [applyToFeed, applyToDetail, refreshCounts],
  );
  const transition = useAlertTransition(applyEverywhere);

  const streamStatus = useEventStream(team, {
    "alert.created": (event) => {
      applyEverywhere(event.alert);
    },
    "alert.updated": (event) => {
      applyEverywhere(event.alert);
    },
    "audit.appended": (event) => {
      applyAudit(event.entry);
    },
    "delivery.updated": (event) => {
      applyDelivery(event.delivery);
    },
    "action_run.updated": (event) => {
      applyActionRun(event.action_run);
    },
    "approval.requested": (event) => {
      applyApproval(event.approval_request);
    },
    "approval.decided": (event) => {
      applyApproval(event.approval_request);
    },
    onReconnect: () => {
      reloadFeed();
      refreshCounts();
      if (selectedAlertId !== null) reloadDetail();
    },
  });

  const select = (id: string | null) => {
    transition.clearError();
    changeWithTransition(() => {
      setSelectedAlertId(id);
    });
  };
  const closeDetail = useCallback(() => {
    changeWithTransition(() => {
      setSelectedAlertId(null);
    });
  }, []);

  const selectedAlert = detail.detail?.alert;
  const isSelected = selectedAlertId !== null;
  const isEmpty = !feed.isLoading && feed.error === null && feed.items.length === 0 && !isSelected;
  const canSend = filter === "open" || filter === "all";

  const openCount = counts?.open;
  const context =
    openCount === undefined
      ? teamLabel
      : `${String(openCount)} open alert${openCount === 1 ? "" : "s"}`;

  return (
    <PageFrame
      title="Inbox"
      context={context}
      onBack={isSelected ? closeDetail : undefined}
      backLabel="Back to the inbox"
      toolbar={
        <InboxToolbar
          filter={filter}
          counts={counts}
          isSending={testAlert.isSending}
          onFilterChange={(next) => {
            setFilter(next);
            closeDetail();
          }}
          onSendTestAlert={() => void testAlert.send()}
        />
      }
      actions={<ConnectionIndicator status={streamStatus} />}
    >
      <div className="flex flex-col gap-6">
        {isSelected ? null : <LivePipelineCard onOpenDetails={onOpenInsights} />}
        {isEmpty ? (
          <InboxEmpty
            canSend={canSend}
            isSending={testAlert.isSending}
            onSend={() => void testAlert.send()}
          />
        ) : (
          <div
            className={
              isSelected
                ? "grid grid-cols-1 items-start gap-5 min-[1100px]:grid-cols-[minmax(340px,2fr)_3fr]"
                : "grid grid-cols-1"
            }
          >
            <div className={isSelected ? "max-[1099px]:hidden" : undefined}>
              <AlertList feed={feed} selectedAlertId={selectedAlertId} onSelect={select} />
            </div>
            {isSelected ? (
              <AlertDetailPane
                detail={detail}
                pendingTransition={transition.pending}
                transitionError={transition.error}
                onTransition={(kind) => {
                  if (selectedAlert) void transition.run(selectedAlert, kind);
                }}
                onClose={closeDetail}
              />
            ) : null}
          </div>
        )}
      </div>
    </PageFrame>
  );
}

function InboxEmpty({
  canSend,
  isSending,
  onSend,
}: {
  canSend: boolean;
  isSending: boolean;
  onSend: () => void;
}) {
  return (
    <Card>
      <EmptyState
        icon="inbox"

        title={canSend ? "All quiet" : "Nothing here"}
        action={
          canSend ? (
            <Button variant="primary" icon="send" isLoading={isSending} onClick={onSend}>
              Send test alert
            </Button>
          ) : undefined
        }
      >
        {canSend
          ? "No alerts right now. Send a test alert to see one arrive."
          : "Alerts you move to this state show up here."}
      </EmptyState>
    </Card>
  );
}

export function AlertsPage({
  teamId,
  teamLabel,
  onOpenInsights,
}: {
  teamId: string;
  teamLabel: string;
  onOpenInsights: () => void;
}) {
  return (
    <TeamInbox key={teamId} team={teamId} teamLabel={teamLabel} onOpenInsights={onOpenInsights} />
  );
}
