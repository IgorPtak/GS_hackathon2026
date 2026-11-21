import { Button } from "../ui/Button";
import { Pill } from "../ui/Pill";
import { ToolbarDivider } from "../ui/Toolbar";
import type { AlertCounts } from "./useAlertCounts";
import type { StatusFilter } from "./useAlertFeed";

const FILTERS: readonly { readonly id: StatusFilter; readonly label: string }[] = [
  { id: "open", label: "Open" },
  { id: "acknowledged", label: "Acknowledged" },
  { id: "resolved", label: "Resolved" },
  { id: "all", label: "All" },
];

function countFor(counts: AlertCounts | null, filter: StatusFilter): number | undefined {
  if (!counts) return undefined;
  return filter === "all" ? counts.open + counts.acknowledged + counts.resolved : counts[filter];
}

interface InboxToolbarProps {
  readonly filter: StatusFilter;
  readonly counts: AlertCounts | null;
  readonly isSending: boolean;
  readonly onFilterChange: (filter: StatusFilter) => void;
  readonly onSendTestAlert: () => void;
}

/** One primary pill, a divider, then the status filters with live counts. */
export function InboxToolbar({
  filter,
  counts,
  isSending,
  onFilterChange,
  onSendTestAlert,
}: InboxToolbarProps) {
  return (
    <div role="toolbar" aria-label="Inbox" className="flex flex-wrap items-center gap-2">
      <Button variant="primary" icon="send" isLoading={isSending} onClick={onSendTestAlert}>
        Send test alert
      </Button>
      <ToolbarDivider />
      {FILTERS.map((option) => (
        <Pill
          key={option.id}
          isActive={filter === option.id}
          count={countFor(counts, option.id)}
          onToggle={() => {
            onFilterChange(option.id);
          }}
        >
          {option.label}
        </Pill>
      ))}
    </div>
  );
}
