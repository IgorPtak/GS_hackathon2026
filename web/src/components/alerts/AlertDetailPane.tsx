import { useEffect } from "react";

import type { Alert, AlertDetail } from "../../api/types";
import { Avatar } from "../ui/Avatar";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { CountBadge } from "../ui/CountBadge";
import { Icon } from "../ui/icons";
import { SeverityDot } from "../ui/SeverityDot";
import { Skeleton } from "../ui/Skeleton";
import { StatusChip } from "../ui/StatusChip";
import { ProposeFixButton } from "../proposals/ProposeFixButton";
import { AlertTechnicalDetails } from "./AlertTechnicalDetails";
import { AlertTimeline } from "./AlertTimeline";
import { GroupMembers } from "./GroupMembers";
import { RunbookChecklist } from "./RunbookChecklist";
import { humanizeId } from "./timelineWords";
import type { AlertDetailApi } from "./useAlertDetail";
import type { AlertTransition } from "./useAlertTransition";

interface AlertDetailPaneProps {
  readonly detail: AlertDetailApi;
  readonly pendingTransition: AlertTransition | null;
  readonly transitionError: string | null;
  readonly onTransition: (transition: AlertTransition) => void;
  readonly onClose: () => void;
}

const STATUS_WORDS: Record<Alert["status"], string> = {
  open: "Open",
  acknowledged: "Acknowledged",
  resolved: "Resolved",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-7">
      <h3 className="mb-3 text-row font-semibold">{title}</h3>
      {children}
    </section>
  );
}

function AlertMeta({ alert }: { alert: Alert }) {
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-meta text-ink-2">
      <span className="inline-flex items-center gap-2">
        <SeverityDot severity={alert.severity} />
        <span className="capitalize">{alert.severity}</span>
      </span>
      <span className="inline-flex items-center gap-2">
        <Avatar name={alert.team} team={alert.team} size="sm" />
        {humanizeId(alert.team)}
      </span>
      {alert.count > 1 ? <CountBadge count={alert.count} /> : null}
      {alert.status !== "open" ? (
        <StatusChip tone={alert.status === "resolved" ? "success" : "info"}>
          {STATUS_WORDS[alert.status]}
        </StatusChip>
      ) : null}
    </div>
  );
}

interface AlertActionsProps {
  readonly alert: Alert;
  readonly pendingTransition: AlertTransition | null;
  readonly onTransition: (transition: AlertTransition) => void;
}

function AlertActions({ alert, pendingTransition, onTransition }: AlertActionsProps) {
  const isBusy = pendingTransition !== null;
  return (
    <div className="mt-5 flex flex-wrap gap-2">
      <Button
        variant="primary"
        isLoading={pendingTransition === "acknowledge"}
        disabled={alert.status !== "open" || isBusy}
        onClick={() => {
          onTransition("acknowledge");
        }}
      >
        Acknowledge
      </Button>
      <Button
        isLoading={pendingTransition === "resolve"}
        disabled={alert.status === "resolved" || isBusy}
        onClick={() => {
          onTransition("resolve");
        }}
      >
        Resolve
      </Button>
      <ProposeFixButton
        alert={alert}
        className="inline-flex h-9 items-center rounded-full bg-fill px-4 text-body font-medium whitespace-nowrap text-ink transition-colors hover:bg-hairline"
      />
    </div>
  );
}

interface AlertDetailBodyProps extends Omit<AlertDetailPaneProps, "onClose"> {
  readonly loaded: AlertDetail;
}

function AlertDetailBody({
  detail,
  loaded,
  pendingTransition,
  transitionError,
  onTransition,
}: AlertDetailBodyProps) {
  const { alert } = loaded;
  return (
    <>
      <h2 className="text-card-title font-semibold break-words">{alert.title}</h2>
      <AlertMeta alert={alert} />
      <AlertActions
        alert={alert}
        pendingTransition={pendingTransition}
        onTransition={onTransition}
      />
      {transitionError ? (
        <p
          role="alert"
          className="mt-3 rounded-input bg-critical/12 px-3 py-2 text-meta text-critical-ink"
        >
          {transitionError}
        </p>
      ) : null}
      {alert.body ? (
        <p className="mt-5 text-body break-words whitespace-pre-wrap text-ink-2">{alert.body}</p>
      ) : null}

      <Section title="What happened">
        <AlertTimeline detail={loaded} />
      </Section>
      {loaded.rendered_runbook ? (
        <Section title="Runbook">
          <p className="-mt-2 mb-3 text-meta text-ink-2">{loaded.rendered_runbook.title}</p>
          <RunbookChecklist
            runbook={loaded.rendered_runbook}
            team={alert.team}
            actionRuns={loaded.action_runs ?? []}
            approvals={loaded.approval_requests ?? []}
            onRunStarted={detail.applyActionRun}
          />
        </Section>
      ) : null}
      {alert.is_group_summary ? (
        <Section title="Grouped alerts">
          <GroupMembers members={alert.group_members ?? []} />
        </Section>
      ) : null}
      <div className="mt-7">
        <AlertTechnicalDetails detail={loaded} />
      </div>
    </>
  );
}

/** Everything about the selected alert: who, what happened, what to do, then the raw details. */
export function AlertDetailPane({
  detail,
  pendingTransition,
  transitionError,
  onTransition,
  onClose,
}: AlertDetailPaneProps) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !document.querySelector("dialog[open]")) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const loaded = detail.detail;

  return (
    <Card className="min-[1100px]:sticky min-[1100px]:top-0 min-[1100px]:max-h-[calc(100dvh-9rem)] min-[1100px]:self-start min-[1100px]:overflow-y-auto">
      <Button variant="ghost" className="-ml-3 mb-3 min-[1100px]:hidden" onClick={onClose}>
        <span className="rotate-90">
          <Icon name="chevron" size={16} />
        </span>
        Inbox
      </Button>

      {detail.error ? (
        <p
          role="alert"
          className="rounded-input bg-warning/20 px-3 py-2 text-meta text-warning-ink"
        >
          Cannot load this alert ({detail.error}).{" "}
          <button type="button" className="font-medium underline" onClick={detail.reload}>
            Try again
          </button>
        </p>
      ) : null}
      {detail.isLoading ? (
        <div className="flex flex-col gap-3" aria-busy="true">
          <Skeleton className="h-8 w-2/3" />
          <Skeleton className="h-5 w-1/3" />
          <Skeleton className="h-40" />
        </div>
      ) : null}

      {loaded ? (
        <AlertDetailBody
          detail={detail}
          loaded={loaded}
          pendingTransition={pendingTransition}
          transitionError={transitionError}
          onTransition={onTransition}
        />
      ) : null}
    </Card>
  );
}
