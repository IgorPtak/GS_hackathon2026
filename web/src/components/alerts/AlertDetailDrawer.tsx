import { useEffect } from "react";

import type { AlertDetailApi } from "./useAlertDetail";
import type { AlertTransition } from "./useAlertTransition";
import { AlertFields } from "./AlertFields";
import { AuditTimeline } from "./AuditTimeline";
import { DeliveryList } from "./DeliveryList";
import { ProposeFixButton } from "../proposals/ProposeFixButton";
import { RunbookPanel } from "../runbooks/RunbookPanel";
import { SeverityBadge } from "./SeverityBadge";

interface AlertDetailDrawerProps {
  detail: AlertDetailApi;
  pendingTransition: AlertTransition | null;
  transitionError: string | null;
  onTransition: (transition: AlertTransition) => void;
  onClose: () => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="mb-2 text-sm font-semibold text-slate-700">{title}</h3>
      {children}
    </section>
  );
}

/** Right-hand drawer (full width on phones) with everything known about one alert. */
export function AlertDetailDrawer({
  detail,
  pendingTransition,
  transitionError,
  onTransition,
  onClose,
}: AlertDetailDrawerProps) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const alert = detail.detail?.alert;
  const isBusy = pendingTransition !== null;

  return (
    <div className="fixed inset-0 z-20 flex justify-end bg-slate-900/30" onClick={onClose}>
      <aside
        role="dialog"
        aria-label="Alert detail"
        onClick={(event) => {
          event.stopPropagation();
        }}
        className="h-full w-full overflow-y-auto bg-white p-4 shadow-xl sm:max-w-xl sm:p-6 lg:max-w-4xl"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="text-lg font-semibold break-words">{alert?.title ?? "Alert"}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-50"
          >
            Close
          </button>
        </div>

        {detail.error ? (
          <p role="alert" className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Cannot load alert ({detail.error}).{" "}
            <button type="button" className="underline" onClick={detail.reload}>
              Retry
            </button>
          </p>
        ) : null}
        {detail.isLoading ? <p className="mt-3 text-sm text-slate-500">Loading alert...</p> : null}

        {alert ? (
          <>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
              <SeverityBadge alert={alert} />
              <span>{alert.status}</span>
              {alert.count > 1 ? (
                <span className="rounded bg-slate-200 px-1.5">×{alert.count}</span>
              ) : null}
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                disabled={alert.status !== "open" || isBusy}
                onClick={() => {
                  onTransition("acknowledge");
                }}
                className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-40"
              >
                {pendingTransition === "acknowledge" ? "Acknowledging..." : "Acknowledge"}
              </button>
              <button
                type="button"
                disabled={alert.status === "resolved" || isBusy}
                onClick={() => {
                  onTransition("resolve");
                }}
                className="rounded border border-slate-400 px-3 py-1.5 text-sm disabled:opacity-40"
              >
                {pendingTransition === "resolve" ? "Resolving..." : "Resolve"}
              </button>
              <ProposeFixButton
                alert={alert}
                className="rounded border border-slate-400 px-3 py-1.5 text-sm hover:bg-slate-50"
              />
            </div>
            {transitionError ? (
              <p role="alert" className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
                {transitionError}
              </p>
            ) : null}
            {alert.body ? (
              <p className="mt-4 text-sm whitespace-pre-wrap break-words">{alert.body}</p>
            ) : null}
            <Section title="Fields">
              <AlertFields alert={alert} />
            </Section>
            <Section title="Runbook">
              <RunbookPanel
                runbook={detail.detail.rendered_runbook}
                team={alert.team}
                actionRuns={detail.detail.action_runs ?? []}
                approvals={detail.detail.approval_requests ?? []}
                onRunStarted={detail.applyActionRun}
              />
            </Section>
            <Section title="Deliveries">
              <DeliveryList deliveries={detail.detail.deliveries} />
            </Section>
            <Section title="Audit">
              <AuditTimeline entries={detail.detail.audit_entries} />
            </Section>
            <details className="mt-5">
              <summary className="cursor-pointer text-sm font-semibold text-slate-700">
                Last event (raw JSON)
              </summary>
              <pre className="mt-2 max-h-80 overflow-auto rounded bg-slate-900 p-3 text-xs text-slate-100">
                {JSON.stringify(alert.last_event, null, 2)}
              </pre>
            </details>
          </>
        ) : null}
      </aside>
    </div>
  );
}
