import type { Alert } from "../../api/types";
import { cx } from "../../lib/cx";
import { Avatar } from "../ui/Avatar";
import { CountBadge } from "../ui/CountBadge";
import { SeverityDot } from "../ui/SeverityDot";
import { StatusChip } from "../ui/StatusChip";
import { formatRelativeTime } from "./alertFormat";
import { humanizeId } from "./timelineWords";

interface AlertListRowProps {
  readonly alert: Alert;
  readonly isSelected: boolean;
  /** True for rows that arrived after the first load; they slide in from the top. */
  readonly isFresh: boolean;
  readonly now: number;
  readonly onSelect: (alertId: string) => void;
}

/** One inbox row: avatar, title with duplicate count, two-line preview, time and severity. */
export function AlertListRow({ alert, isSelected, isFresh, now, onSelect }: AlertListRowProps) {
  const memberCount = alert.group_members?.length ?? 0;
  const preview = alert.body.trim() || `From ${humanizeId(alert.source_id)}`;
  return (
    <li className={cx(isFresh && "animate-row-in")}>
      <button
        type="button"
        aria-current={isSelected || undefined}
        onClick={() => {
          onSelect(alert.id);
        }}
        className={cx(
          "flex w-full items-start gap-3 rounded-tile px-3 py-3.5 text-left transition-colors",
          isSelected ? "bg-fill" : "hover:bg-fill/60",
        )}
      >
        <Avatar name={alert.team} team={alert.team} size="lg" />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate text-row font-semibold max-sm:line-clamp-2 max-sm:whitespace-normal">
                {alert.title}
              </span>
              {alert.count > 1 ? <CountBadge count={alert.count} /> : null}
            </span>
            <span className="flex shrink-0 items-center gap-2 text-meta text-ink-2">
              <SeverityDot severity={alert.severity} />
              <span className="num" title={new Date(alert.last_seen).toLocaleString()}>
                {formatRelativeTime(alert.last_seen, now)}
              </span>
            </span>
          </span>
          <span className="line-clamp-2 text-body text-ink-2">{preview}</span>
          {alert.status !== "open" || alert.is_group_summary ? (
            <span className="mt-0.5 flex flex-wrap gap-2">
              {alert.status !== "open" ? (
                <StatusChip
                  tone={alert.status === "resolved" ? "success" : "info"}
                  icon={alert.status === "resolved" ? "check" : undefined}
                >
                  {alert.status === "resolved" ? "Resolved" : "Acknowledged"}
                </StatusChip>
              ) : null}
              {alert.is_group_summary ? <StatusChip>{memberCount} grouped</StatusChip> : null}
            </span>
          ) : null}
        </span>
      </button>
    </li>
  );
}
