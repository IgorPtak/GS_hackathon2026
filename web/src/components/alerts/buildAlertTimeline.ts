import type { ActionRun, AlertDetail, AuditEntry } from "../../api/types";
import type { StepState } from "../ui/TimelineStep";
import {
  actionWords,
  approvalViaWords,
  deliveryWords,
  humanizeId,
  personName,
} from "./timelineWords";

export interface TimelineItem {
  readonly key: string;
  /** ISO time; the list is sorted by it. */
  readonly at: string;
  readonly state: StepState;
  readonly title: string;
}

function fromAudit(entry: AuditEntry): TimelineItem | null {
  const state: StepState =
    entry.outcome === "error" ? "failed" : entry.outcome === "pending" ? "running" : "done";
  const who = personName(entry.actor.id, entry.actor.display_name);
  const titles: Partial<Record<AuditEntry["verb"], string>> = {
    alert_created: "Alert created",
    alert_grouped: "Grouped with similar alerts",
    alert_acknowledged: `Acknowledged by ${who}`,
    alert_resolved: `Resolved by ${who}`,
    runbook_started: "Runbook started",
    fix_proposed: "Fix proposed",
    fix_decided: "Fix proposal decided",
  };
  const title = titles[entry.verb];
  // Deliveries, action runs and approvals have richer rows of their own; skip their audit echo.
  return title ? { key: `audit-${String(entry.id)}`, at: entry.at, state, title } : null;
}

function approverFor(detail: AlertDetail, run: ActionRun): string | null {
  const request = (detail.approval_requests ?? []).find((item) => item.action_run_id === run.id);
  if (!request) return null;
  const delivery = detail.deliveries.find((item) => item.purpose === "approval_request");
  return delivery?.recipient_id ? personName(delivery.recipient_id) : null;
}

function fromActionRun(detail: AlertDetail, run: ActionRun): TimelineItem | null {
  const words = actionWords(run.action_id);
  const step = detail.rendered_runbook?.steps.find((item) => item.index === run.step_index);
  const attempts =
    step && step.max_attempts > 1
      ? ` (${String(run.attempt)} of ${String(step.max_attempts)})`
      : "";
  const base = { key: `run-${run.id}`, at: run.updated_at };
  switch (run.status) {
    case "pending_approval": {
      const approver = approverFor(detail, run);
      const title = approver
        ? `Waiting for ${approver} to approve ${words.noun}`
        : `Waiting for approval of ${words.noun}`;
      return { ...base, state: "running", title };
    }
    case "approved":
    case "rejected":
      return null;
    case "running":
      return { ...base, state: "running", title: words.running };
    case "succeeded":
      return { ...base, state: "done", title: words.done };
    case "failed":
      return { ...base, state: "failed", title: `${words.failed}${attempts}` };
    case "skipped":
      return { ...base, state: "skipped", title: words.skipped };
  }
}

/** Joins audit entries, deliveries, action runs and approvals into one plain-language story. */
export function buildAlertTimeline(detail: AlertDetail): readonly TimelineItem[] {
  const { alert } = detail;
  const items: TimelineItem[] = [
    {
      key: "received",
      at: alert.first_seen,
      state: "done",
      title: `Event received from ${humanizeId(alert.source_id)}`,
    },
  ];
  for (const entry of detail.audit_entries) {
    const item = fromAudit(entry);
    if (item) items.push(item);
  }
  for (const delivery of detail.deliveries) {
    const { title, state } = deliveryWords(delivery);
    items.push({
      key: `delivery-${String(delivery.id)}`,
      at: delivery.delivered_at ?? delivery.updated_at,
      state,
      title,
    });
  }
  for (const run of detail.action_runs ?? []) {
    const item = fromActionRun(detail, run);
    if (item) items.push(item);
  }
  for (const request of detail.approval_requests ?? []) {
    if (request.decision === null || request.decided_at === null) continue;
    const who = request.decided_by
      ? personName(request.decided_by.id, request.decided_by.display_name)
      : "someone";
    const verb = request.decision === "approve" ? "Approved" : "Rejected";
    items.push({
      key: `approval-${request.id}`,
      at: request.decided_at,
      state: request.decision === "approve" ? "done" : "failed",
      title: `${verb} by ${who} ${approvalViaWords(request.decided_via)}`.trim(),
    });
  }
  return items
    .map((item, index) => ({ item, index }))
    .sort((a, b) => Date.parse(a.item.at) - Date.parse(b.item.at) || a.index - b.index)
    .map(({ item }) => item);
}
