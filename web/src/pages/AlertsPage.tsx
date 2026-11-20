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
import { RecentEventsPanel } from "../components/events/RecentEventsPanel";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { EmptyState } from "../components/ui/EmptyState";
import { Icon } from "../components/ui/icons";
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
function TeamInbox({ team, teamLabel }: { team: string; teamLabel: string }) {
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

  return (
    <div className="flex flex-col gap-5">
      <div
        className={isSelected ? "flex flex-col gap-5 max-[1099px]:hidden" : "flex flex-col gap-5"}
      >
        <LivePipelineCard teamId={team} teamLabel={teamLabel} />
        <InboxToolbar
          filter={filter}
          counts={counts}
          streamStatus={streamStatus}
          isSending={testAlert.isSending}
          onFilterChange={setFilter}
          onSendTestAlert={() => void testAlert.send()}
        />
      </div>

      {isEmpty ? (
        <Card>
          <EmptyState
            icon="inbox"
            action={
              canSend ? (
                <Button
                  variant="primary"
                  icon="send"
                  isLoading={testAlert.isSending}
                  onClick={() => void testAlert.send()}
                >
                  Send test alert
                </Button>
              ) : undefined
            }
          >
            {canSend
              ? "No alerts right now. Send a test alert to see one arrive."
              : "Nothing here yet. Alerts you move to this state will show up here."}
          </EmptyState>
        </Card>
      ) : (
        <div className="grid grid-cols-1 items-start gap-4 min-[1100px]:grid-cols-[minmax(340px,2fr)_3fr]">
          <div className={isSelected ? "max-[1099px]:hidden" : undefined}>
            <AlertList feed={feed} selectedAlertId={selectedAlertId} onSelect={select} />
          </div>
          <div className={isSelected ? undefined : "max-[1099px]:hidden"}>
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
            ) : (
              <Card className="flex flex-col items-center gap-3 py-16 text-center text-ink-2">
                <Icon name="inbox" size={28} />
                <p className="text-body">Pick an alert to see what happened and what to do next.</p>
              </Card>
            )}
          </div>
        </div>
      )}

      <details
        className={`group rounded-card border border-hairline bg-card px-6 py-4 ${isSelected ? "max-[1099px]:hidden" : ""}`}
      >
        <summary className="flex list-none items-center justify-between text-body font-medium [&::-webkit-details-marker]:hidden">
          Recent events
          <span className="text-ink-2 transition-transform group-open:rotate-180">
            <Icon name="chevron" size={18} />
          </span>
        </summary>
        <div className="mt-3">
          <RecentEventsPanel />
        </div>
      </details>
    </div>
  );
}

export function AlertsPage({ teamId, teamLabel }: { teamId: string; teamLabel: string }) {
  return <TeamInbox key={teamId} team={teamId} teamLabel={teamLabel} />;
}
