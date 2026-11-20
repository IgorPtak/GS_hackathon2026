import type { ApprovalRequest } from "../../api/types";
import { formatDateTime, formatRelativeTime } from "../alerts/alertFormat";
import { Icon } from "../ui/icons";
import { StatusChip } from "../ui/StatusChip";

interface RecentDecisionsListProps {
  readonly items: readonly ApprovalRequest[];
}

const CHANNEL_LABEL: Record<NonNullable<ApprovalRequest["decided_via"]>, string> = {
  ui: "UI",
  phone: "phone",
  sms: "SMS",
};

/** Collapsible list of recently decided runbook approvals with actor and channel. */
export function RecentDecisionsList({ items }: RecentDecisionsListProps) {
  if (items.length === 0) return null;

  return (
    <details className="group rounded-card border border-hairline bg-card shadow-card">
      <summary className="flex list-none items-center gap-2.5 px-6 py-4 text-body font-medium text-ink select-none [&::-webkit-details-marker]:hidden">
        <Icon
          name="chevron"
          size={16}
          className="shrink-0 -rotate-90 text-ink-2 transition-transform group-open:rotate-0"
        />
        <span>Recent decisions</span>
        <span className="num rounded-full bg-fill px-2 py-0.5 text-caption font-medium text-ink-2">
          {items.length}
        </span>
      </summary>
      <div className="border-t border-hairline px-4 py-2">
        <ul className="divide-y divide-hairline">
          {items.map((item) => {
            const isApproved = item.decision === "approve";
            const actor = item.decided_by?.display_name ?? item.decided_by?.id ?? "Unknown";
            const via = item.decided_via ? CHANNEL_LABEL[item.decided_via] : null;
            const timestamp = item.decided_at ?? item.requested_at;
            return (
              <li
                key={item.id}
                className="flex flex-wrap items-center justify-between gap-3 px-2 py-3.5"
              >
                <div className="min-w-0 flex-1 space-y-0.5">
                  <p className="text-body font-medium break-words text-ink">{item.summary}</p>
                  <p className="text-meta text-ink-2">
                    {isApproved ? "Approved" : "Rejected"} by {actor}
                    {via ? ` via ${via}` : ""}
                    {item.comment ? ` · “${item.comment}”` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <StatusChip
                    tone={isApproved ? "success" : "neutral"}
                    icon={isApproved ? "check" : "cross"}
                  >
                    {isApproved ? "Approved" : "Rejected"}
                  </StatusChip>
                  <time
                    dateTime={timestamp}
                    title={formatDateTime(timestamp)}
                    className="num text-meta text-ink-3"
                  >
                    {formatRelativeTime(timestamp)}
                  </time>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </details>
  );
}
