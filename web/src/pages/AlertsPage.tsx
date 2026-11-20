import { useCallback, useState } from "react";

import type { Alert } from "../api/types";
import { AlertDetailDrawer } from "../components/alerts/AlertDetailDrawer";
import { AlertFeed } from "../components/alerts/AlertFeed";
import { useAlertDetail } from "../components/alerts/useAlertDetail";
import { useAlertFeed, type StatusFilter } from "../components/alerts/useAlertFeed";
import { useAlertTransition } from "../components/alerts/useAlertTransition";
import { useEventStream } from "../hooks/useEventStream";

/** Alerts tab body for one team; the single SSE connection fans out to the feed and the drawer. */
function TeamAlerts({ team }: { team: string }) {
  const [filter, setFilter] = useState<StatusFilter>("open");
  const [selectedAlertId, setSelectedAlertId] = useState<string | null>(null);
  const feed = useAlertFeed(team, filter);
  const detail = useAlertDetail(selectedAlertId);
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
    },
    [applyToFeed, applyToDetail],
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
      if (selectedAlertId !== null) reloadDetail();
    },
  });

  const selectedAlert = detail.detail?.alert;
  return (
    <>
      <AlertFeed
        feed={feed}
        filter={filter}
        streamStatus={streamStatus}
        selectedAlertId={selectedAlertId}
        onFilterChange={setFilter}
        onSelect={(id) => {
          transition.clearError();
          setSelectedAlertId(id);
        }}
      />
      {selectedAlertId !== null ? (
        <AlertDetailDrawer
          detail={detail}
          pendingTransition={transition.pending}
          transitionError={transition.error}
          onTransition={(kind) => {
            if (selectedAlert) void transition.run(selectedAlert, kind);
          }}
          onClose={() => {
            setSelectedAlertId(null);
          }}
        />
      ) : null}
    </>
  );
}

export function AlertsPage({ teamId }: { teamId: string | null }) {
  if (teamId === null) {
    return (
      <section className="rounded-lg border border-dashed border-slate-300 bg-white p-6">
        <h2 className="text-xl font-semibold">Alerts</h2>
        <p className="mt-2 text-sm text-slate-600">Select a team to see its alerts.</p>
      </section>
    );
  }
  return <TeamAlerts key={teamId} team={teamId} />;
}
