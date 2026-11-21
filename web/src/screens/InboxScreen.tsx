import { AlertsPage } from "../pages/AlertsPage";
import type { ScreenProps } from "./types";

/** Inbox screen: the page renders its own frame, since its header shows live counts. */
export function InboxScreen({ teamId, teamLabel, onNavigate }: ScreenProps) {
  return (
    <AlertsPage
      teamId={teamId}
      teamLabel={teamLabel}
      onOpenInsights={() => {
        onNavigate("insights");
      }}
    />
  );
}
