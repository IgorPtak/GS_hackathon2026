import type { RunbookSummary } from "../../api/types";
import { Avatar } from "../ui/Avatar";
import { Icon } from "../ui/icons";
import { StatusChip } from "../ui/StatusChip";
import { formatLabel, normalizedByLabel, stepCountLabel, teamName } from "./runbookFormat";

/** Summary card of one runbook in the list. */
export function RunbookCard({ item, onOpen }: { item: RunbookSummary; onOpen: () => void }) {
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex h-full w-full flex-col gap-4 rounded-card border border-hairline bg-card p-5 text-left shadow-card transition-colors hover:border-ink-3"
      >
        <div className="flex items-start gap-3">
          <Avatar name={item.team ?? item.title} team={item.team} size="lg" />
          <div className="min-w-0 flex-1">
            <p className="text-row font-semibold break-words">{item.title}</p>
            <p className="text-meta text-ink-2">{item.team ? teamName(item.team) : "Any team"}</p>
          </div>
          <Icon name="arrowRight" size={18} className="mt-1 shrink-0 text-ink-3" />
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-2">
          <StatusChip>{stepCountLabel(item.step_count)}</StatusChip>
          <StatusChip>{formatLabel(item.format)}</StatusChip>
          <StatusChip
            tone={item.normalized_by === "llm" ? "info" : "neutral"}
            icon={item.normalized_by === "llm" ? "sparkle" : undefined}
          >
            {normalizedByLabel(item.normalized_by)}
          </StatusChip>
        </div>
      </button>
    </li>
  );
}
