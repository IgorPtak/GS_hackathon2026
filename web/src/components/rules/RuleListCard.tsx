import type { RuleRecord } from "../../api/types";
import { Avatar } from "../ui/Avatar";
import { Icon } from "../ui/icons";
import { SeverityDot } from "../ui/SeverityDot";
import { StatusChip } from "../ui/StatusChip";
import { channelsSummary, ruleName, severityLabel } from "./ruleLabels";

/** One rule as a card: name, description, state, severity, channels and linked runbook. */
export function RuleListCard({
  record,
  onOpen,
}: {
  readonly record: RuleRecord;
  readonly onOpen: () => void;
}) {
  const { rule } = record;
  return (
    <li>
      <button
        type="button"
        onClick={onOpen}
        className="flex w-full items-start gap-4 rounded-card border border-hairline bg-card p-5 text-left shadow-card transition-colors hover:border-ink-3"
      >
        <Avatar name={rule.team} team={rule.team} size="lg" />
        <span className="min-w-0 flex-1 space-y-1.5">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-row font-semibold">{ruleName(record.id)}</span>
            <StatusChip tone={rule.enabled ? "success" : "neutral"}>
              {rule.enabled ? "Enabled" : "Disabled"}
            </StatusChip>
          </span>
          <span className="line-clamp-2 block text-body text-ink-2">
            {rule.description || "No description yet."}
          </span>
          <span className="flex flex-wrap items-center gap-x-5 gap-y-1 pt-1 text-meta text-ink-2">
            <span className="inline-flex items-center gap-2">
              {rule.severity ? <SeverityDot severity={rule.severity} /> : null}
              {severityLabel(rule)}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Icon name="send" size={14} />
              {channelsSummary(rule)}
            </span>
            {rule.runbook ? (
              <span className="inline-flex items-center gap-1.5">
                <Icon name="runbook" size={14} />
                {rule.runbook}
              </span>
            ) : null}
          </span>
        </span>
        <Icon name="chevron" size={18} className="mt-1 -rotate-90 text-ink-3" />
      </button>
    </li>
  );
}
