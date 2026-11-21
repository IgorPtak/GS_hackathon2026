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
        className="group flex h-full w-full flex-col gap-4 rounded-card border border-hairline bg-card p-5 text-left shadow-card transition-[border-color,box-shadow,translate] duration-300 hover:-translate-y-0.5 hover:shadow-tile active:translate-y-0"
      >
        <div className="flex items-start gap-3">
          <Avatar name={item.team ?? item.title} team={item.team} size="md" />
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 text-body font-semibold" title={item.title}>
              {item.title}
            </p>
            <p className="text-meta text-ink-2">{item.team ? teamName(item.team) : "Any team"}</p>
          </div>
          <Icon
            name="arrowRight"
            size={18}
            className="mt-0.5 shrink-0 text-ink-3 transition-[translate,color] duration-300 group-hover:translate-x-0.5 group-hover:text-ink"
          />
        </div>
        <div className="mt-auto flex flex-wrap items-center gap-2">
          <StatusChip>{stepCountLabel(item.step_count)}</StatusChip>
          <StatusChip>{formatLabel(item.format)}</StatusChip>
          {item.normalized_by === "llm" ? (
            <StatusChip tone="info" icon="sparkle">
              {normalizedByLabel(item.normalized_by)}
            </StatusChip>
          ) : null}
        </div>
      </button>
    </li>
  );
}
