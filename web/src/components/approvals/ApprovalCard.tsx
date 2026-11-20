import { useState } from "react";

import type { ApprovalRequest } from "../../api/types";
import { formatDateTime } from "../alerts/alertFormat";
import type { DecisionKind } from "./useApprovalDecision";

interface ApprovalCardProps {
  request: ApprovalRequest;
  isBusy: boolean;
  error: string | null;
  onDecide: (decision: DecisionKind, comment: string) => void;
}

/** One pending approval: what will run, the code to reply with, and Approve / Reject. */
export function ApprovalCard({ request, isBusy, error, onDecide }: ApprovalCardProps) {
  const [comment, setComment] = useState("");
  const params = Object.entries(request.params ?? {});
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 font-medium break-words">{request.summary}</p>
        <span className="rounded bg-amber-100 px-2 py-0.5 font-mono text-sm text-amber-900">
          {request.approval_code}
        </span>
      </div>
      <p className="mt-1 font-mono text-xs break-words text-slate-600">
        {request.action_id}
        {params.length > 0 ? ` (${params.map(([k, v]) => `${k}=${v}`).join(", ")})` : ""}
      </p>
      <p className="mt-1 text-xs text-slate-500">
        Requested {formatDateTime(request.requested_at)} · alert{" "}
        <span className="font-mono">{request.alert_id}</span> · step #{request.step_index + 1}
      </p>
      <label className="mt-3 block text-sm">
        <span className="sr-only">Comment</span>
        <input
          type="text"
          value={comment}
          placeholder="Comment (optional)"
          onChange={(event) => {
            setComment(event.target.value);
          }}
          className="w-full rounded border border-slate-300 px-2 py-1"
        />
      </label>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={isBusy}
          onClick={() => {
            onDecide("approve", comment);
          }}
          className="rounded bg-green-700 px-3 py-1.5 text-sm text-white disabled:opacity-40"
        >
          Approve
        </button>
        <button
          type="button"
          disabled={isBusy}
          onClick={() => {
            onDecide("reject", comment);
          }}
          className="rounded border border-red-600 px-3 py-1.5 text-sm text-red-700 disabled:opacity-40"
        >
          Reject
        </button>
      </div>
      {error ? (
        <p role="alert" className="mt-2 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
          {error}
        </p>
      ) : null}
    </li>
  );
}
