import { useState } from "react";

import type { Alert } from "../../api/types";
import { formatRelativeTime } from "./alertFormat";
import { ProposeFixButton } from "../proposals/ProposeFixButton";
import { GroupMembers } from "./GroupMembers";
import { SeverityBadge } from "./SeverityBadge";

interface AlertRowProps {
  alert: Alert;
  isSelected: boolean;
  now: number;
  onSelect: (alertId: string) => void;
}

/** One feed row; group summaries get a chevron that reveals their members. */
export function AlertRow({ alert, isSelected, now, onSelect }: AlertRowProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const members = alert.group_members ?? [];

  return (
    <li className={isSelected ? "bg-sky-50" : undefined}>
      <div className="flex items-start gap-1 px-2 py-2 sm:px-3">
        {alert.is_group_summary ? (
          <button
            type="button"
            aria-expanded={isExpanded}
            aria-label={isExpanded ? "Collapse group" : "Expand group"}
            onClick={() => {
              setIsExpanded((value) => !value);
            }}
            className="mt-0.5 h-6 w-6 shrink-0 rounded text-slate-500 hover:bg-slate-100"
          >
            <span
              aria-hidden
              className={`inline-block transition-transform ${isExpanded ? "rotate-90" : ""}`}
            >
              ›
            </span>
          </button>
        ) : (
          <span className="w-6 shrink-0" />
        )}
        <button
          type="button"
          onClick={() => {
            onSelect(alert.id);
          }}
          className="flex min-w-0 flex-1 flex-col gap-1 text-left"
        >
          <span className="flex flex-wrap items-center gap-2">
            <SeverityBadge alert={alert} />
            <span className="min-w-0 font-medium break-words">{alert.title}</span>
            {alert.count > 1 ? (
              <span className="rounded bg-slate-200 px-1.5 text-xs leading-5 font-medium">
                ×{alert.count}
              </span>
            ) : null}
            {alert.is_group_summary ? (
              <span className="text-xs text-slate-500">{members.length} grouped</span>
            ) : null}
          </span>
          <span className="flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-slate-600">
            <span>{alert.status}</span>
            <span title={new Date(alert.last_seen).toLocaleString()}>
              {formatRelativeTime(alert.last_seen, now)}
            </span>
            <span>{alert.team}</span>
          </span>
        </button>
        <ProposeFixButton alert={alert} />
      </div>
      {alert.is_group_summary && isExpanded ? <GroupMembers members={members} now={now} /> : null}
    </li>
  );
}
