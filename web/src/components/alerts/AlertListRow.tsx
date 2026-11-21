import type { Alert } from "../../api/types";
import { cx } from "../../lib/cx";
import { Avatar } from "../ui/Avatar";
import { CountBadge } from "../ui/CountBadge";
import { SeverityDot } from "../ui/SeverityDot";
import { StatusChip } from "../ui/StatusChip";
import { formatRelativeTime } from "./alertFormat";
import { readableText, splitAlertTitle } from "./alertText";
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
  const text = splitAlertTitle(alert.title);
  const body = alert.body.trim() || `From ${humanizeId(alert.source_id)}`;
  const preview = text.reason ? `${text.reason}. ${body}` : body;
  return (
    <li className={cx(isFresh && "animate-row-in")}>
      <button
        type="button"
        aria-current={isSelected || undefined}
        onClick={() => {
          onSelect(alert.id);
        }}
        className={cx(
          "flex w-full items-start gap-3.5 rounded-[16px] border px-4 py-3.5 text-left transition-[background-color,border-color,box-shadow] duration-200",
          isSelected
            ? "border-hairline bg-card shadow-tile"
            : "border-transparent hover:bg-card/70",
        )}
      >
        <Avatar name={alert.team} team={alert.team} size="md" />
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-center justify-between gap-3">
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate text-body font-semibold max-sm:line-clamp-2 max-sm:whitespace-normal">
                {text.title}
              </span>
              {alert.count > 1 ? <CountBadge count={alert.count} /> : null}
            </span>
            <span className="flex shrink-0 items-center gap-1.5 text-caption text-ink-2">
              <SeverityDot severity={alert.severity} />
              <span className="num" title={new Date(alert.last_seen).toLocaleString()}>
                {formatRelativeTime(alert.last_seen, now)}
              </span>
            </span>
          </span>
          <span className="line-clamp-2 text-meta text-ink-2">{readableText(preview)}</span>
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
