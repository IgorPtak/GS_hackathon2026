import { useApprovals } from "../approvals/useApprovals";
import { useEventStream } from "../../hooks/useEventStream";
import { RailItem } from "../ui/RailItem";

interface ApprovalsRailItemProps {
  readonly team: string;
  readonly href: string;
  readonly isActive: boolean;
  readonly onSelect: () => void;
}

/** Approvals rail link with a live count of the team's pending requests. */
export function ApprovalsRailItem({ team, href, isActive, onSelect }: ApprovalsRailItemProps) {
  const { items, apply, reload } = useApprovals(team);
  useEventStream(team, {
    "approval.requested": (event) => {
      apply(event.approval_request);
    },
    "approval.decided": (event) => {
      apply(event.approval_request);
    },
    onReconnect: reload,
  });

  return (
    <RailItem
      label="Approvals"
      icon="approval"
      href={href}
      isActive={isActive}
      badge={items.length}
      onSelect={onSelect}
    />
  );
}
