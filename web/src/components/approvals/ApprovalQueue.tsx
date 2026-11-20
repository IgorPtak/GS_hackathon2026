import { useEventStream } from "../../hooks/useEventStream";
import { ConnectionIndicator } from "../alerts/ConnectionIndicator";
import { ApprovalCard } from "./ApprovalCard";
import { useApprovalDecision } from "./useApprovalDecision";
import { useApprovals } from "./useApprovals";

/** Pending approvals of one team, live from approval.requested / approval.decided. */
export function ApprovalQueue({ team }: { team: string }) {
  const approvals = useApprovals(team);
  const { apply, reload } = approvals;
  const decision = useApprovalDecision(team, apply);
  const streamStatus = useEventStream(team, {
    "approval.requested": (event) => {
      apply(event.approval_request);
    },
    "approval.decided": (event) => {
      apply(event.approval_request);
    },
    onReconnect: reload,
  });

  return (
    <section aria-labelledby="approvals-title">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 id="approvals-title" className="text-xl font-semibold">
          Approvals
        </h2>
        <ConnectionIndicator status={streamStatus} />
      </div>
      {approvals.isLoading ? <p className="text-sm text-slate-500">Loading approvals...</p> : null}
      {approvals.error ? (
        <p role="alert" className="mb-3 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          Cannot load approvals ({approvals.error}).{" "}
          <button type="button" className="underline" onClick={approvals.reload}>
            Retry
          </button>
        </p>
      ) : null}
      {!approvals.isLoading && !approvals.error && approvals.items.length === 0 ? (
        <p className="text-sm text-slate-500">No pending approvals</p>
      ) : null}
      <ul className="space-y-3">
        {approvals.items.map((request) => (
          <ApprovalCard
            key={request.id}
            request={request}
            isBusy={decision.busyId === request.id}
            error={decision.errors[request.id] || null}
            onDecide={(kind, comment) => {
              void decision.decide(request.id, kind, comment);
            }}
          />
        ))}
      </ul>
    </section>
  );
}
