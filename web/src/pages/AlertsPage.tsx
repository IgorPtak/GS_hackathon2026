import { useCallback, useState } from "react";
import { flushSync } from "react-dom";

import type { Alert } from "../api/types";
import { AlertDetailPane } from "../components/alerts/AlertDetailPane";
import { AlertList } from "../components/alerts/AlertList";
import { InboxToolbar } from "../components/alerts/InboxToolbar";
import { useAlertCounts } from "../components/alerts/useAlertCounts";
import { useAlertDetail } from "../components/alerts/useAlertDetail";
import { useAlertFeed, type StatusFilter } from "../components/alerts/useAlertFeed";
import { useAlertTransition } from "../components/alerts/useAlertTransition";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { Icon } from "../components/ui/icons";
import { cx } from "../lib/cx";
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

  const openCount = counts?.open;
  const context =
    openCount === undefined
      ? teamLabel
      : openCount === 0
        ? "all clear"
        : `${String(openCount)} open`;

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
          onFilterChange={(next) => {
            setFilter(next);
            closeDetail();
          }}
        />
      }
      actions={<ConnectionIndicator status={streamStatus} />}
      isFlush
    >
      {isEmpty ? (
        <div className="flex flex-1 items-center justify-center overflow-y-auto p-10">
          <InboxEmpty
            isOpenView={filter === "open" || filter === "all"}
            onOpenInsights={onOpenInsights}
          />
        </div>
      ) : (
        <>
          <section
            aria-label="Alerts"
            className={cx(
              "min-h-0 w-full overflow-y-auto overscroll-contain bg-panel min-[1100px]:w-[420px] min-[1100px]:shrink-0 min-[1100px]:border-r min-[1100px]:border-hairline",
              isSelected && "max-[1099px]:hidden",
            )}
          >
            <div key={filter} className="animate-fade-in">
              <AlertList feed={feed} selectedAlertId={selectedAlertId} onSelect={select} />
            </div>
          </section>
          <section
            aria-label="Alert details"
            className={cx(
              "min-h-0 min-w-0 flex-1 overflow-y-auto overscroll-contain",
              isSelected ? "bg-card" : "max-[1099px]:hidden",
            )}
          >
            {isSelected ? (
              <AlertDetailPane
                key={selectedAlertId}
                detail={detail}
                pendingTransition={transition.pending}
                transitionError={transition.error}
                onTransition={(kind) => {
                  if (selectedAlert) void transition.run(selectedAlert, kind);
                }}
                onClose={closeDetail}
              />
            ) : (
              <NothingSelected />
            )}
          </section>
        </>
      )}
    </PageFrame>
  );
}

/** The calm right pane before anything is picked; the panel's star sky shows through. */
function NothingSelected() {
  return (
    <div className="flex h-full animate-fade-in flex-col items-center justify-center gap-3 p-10 text-center">
      <span className="flex size-16 items-center justify-center rounded-full bg-card/80 text-ink-3 shadow-tile backdrop-blur">
        <Icon name="inbox" size={28} />
      </span>
      <p className="text-body font-medium text-ink-2">Pick an alert to see what happened</p>
      <p className="max-w-xs text-meta text-ink-3">
        Who was told, which runbook started, and what to do next.
      </p>
    </div>
  );
}

function InboxEmpty({
  isOpenView,
  onOpenInsights,
}: {
  isOpenView: boolean;
  onOpenInsights: () => void;
}) {
  return (
    <div className="w-full max-w-md animate-fade-up">
      <EmptyState
        icon="check"
        title={isOpenView ? "All quiet" : "Nothing here"}
        action={
          isOpenView ? (
            <Button variant="raised" icon="insights" onClick={onOpenInsights}>
              See how the pipeline is doing
            </Button>
          ) : undefined
        }
      >
        {isOpenView
          ? "No open alerts. New ones appear here the moment they arrive."
          : "Alerts you move to this state show up here."}
      </EmptyState>
    </div>
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
