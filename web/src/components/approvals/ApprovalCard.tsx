import { useState } from "react";

import type { ApprovalRequest } from "../../api/types";
import { formatDateTime, formatRelativeTime } from "../alerts/alertFormat";
import { Avatar } from "../ui/Avatar";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { TextInput } from "../ui/TextInput";
import type { DecisionKind } from "./useApprovalDecision";

interface ApprovalCardProps {
  readonly request: ApprovalRequest;
  readonly alertTitle: string;
  readonly runbookTitle: string;
  readonly busyKind: DecisionKind | null;
  readonly error: string | null;
  readonly onOpenAlert: (alertId: string) => void;
  readonly onDecide: (decision: DecisionKind, comment: string) => void;
}

/** Reads the summary as a direct question when it is not already phrased as one. */
function formatAsQuestion(summary: string): string {
  const trimmed = summary.trim().replace(/\.+$/, "");
  if (!trimmed) return "Approve this step?";
  return trimmed.endsWith("?") ? trimmed : `${trimmed}?`;
}

/** One pending approval card framed as a question, with context, quiet phone code and actions. */
export function ApprovalCard({
  request,
  alertTitle,
  runbookTitle,
  busyKind,
  error,
  onOpenAlert,
  onDecide,
}: ApprovalCardProps) {
  const [comment, setComment] = useState("");
  const isBusy = busyKind !== null;

  return (
    <Card as="li" className="list-none space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3.5">
          <Avatar name={request.team} team={request.team} size="md" className="mt-0.5" />
          <div className="min-w-0 space-y-1">
            <h3 className="text-row font-semibold break-words text-ink">
              {formatAsQuestion(request.summary)}
            </h3>
            <p className="text-meta text-ink-2">
              {runbookTitle} · Step {request.step_index + 1} ·{" "}
              <time dateTime={request.requested_at} title={formatDateTime(request.requested_at)}>
                {formatRelativeTime(request.requested_at)}
              </time>
            </p>
          </div>
        </div>
        <span
          className="num shrink-0 rounded-full bg-fill px-2.5 py-1 text-caption font-medium text-ink-2"
          title="4-digit code for SMS or phone reply"
        >
          Code <span className="font-mono text-ink">{request.approval_code}</span>
        </span>
      </div>

      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 rounded-tile bg-panel px-3.5 py-2.5 text-meta">
        <span className="font-medium text-ink-2">Alert</span>
        <button
          type="button"
          onClick={() => {
            onOpenAlert(request.alert_id);
          }}
          className="min-w-0 text-left font-medium break-words text-accent-ink hover:underline"
        >
          {alertTitle}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 pt-1">
        <div className="min-w-[12rem] flex-1">
          <label className="sr-only" htmlFor={`note-${request.id}`}>
            Optional note
          </label>
          <TextInput
            id={`note-${request.id}`}
            type="text"
            value={comment}
            placeholder="Add a note (optional)"
            disabled={isBusy}
            onChange={(event) => {
              setComment(event.target.value);
            }}
            className="h-9 text-meta"
          />
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            disabled={isBusy}
            isLoading={busyKind === "reject"}
            onClick={() => {
              onDecide("reject", comment);
            }}
          >
            Reject
          </Button>
          <Button
            variant="primary"
            disabled={isBusy}
            isLoading={busyKind === "approve"}
            onClick={() => {
              onDecide("approve", comment);
            }}
          >
            Approve
          </Button>
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          className="rounded-tile border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-meta text-warning-ink"
        >
          {error}
        </p>
      ) : null}
    </Card>
  );
}
