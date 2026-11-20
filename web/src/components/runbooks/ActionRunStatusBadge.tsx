import type { ActionRunStatus } from "../../api/types";

const CLASSES: Record<ActionRunStatus, string> = {
  pending_approval: "bg-amber-100 text-amber-800",
  approved: "bg-blue-100 text-blue-800",
  rejected: "bg-red-100 text-red-800",
  running: "bg-blue-100 text-blue-800",
  succeeded: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
  skipped: "bg-slate-100 text-slate-500",
};

export function ActionRunStatusBadge({ status }: { status: ActionRunStatus }) {
  return (
    <span className={`rounded px-1.5 text-xs leading-5 ${CLASSES[status]}`}>
      {status.replaceAll("_", " ")}
    </span>
  );
}
