import { AlertsPage } from "../pages/AlertsPage";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Inbox screen: live pipeline card, alert list and detail pane, recent events below. */
export function InboxScreen({ teamId, teamLabel }: ScreenProps) {
  return (
    <PageFrame title="Inbox" context={teamLabel}>
      <AlertsPage teamId={teamId} teamLabel={teamLabel} />
    </PageFrame>
  );
}
