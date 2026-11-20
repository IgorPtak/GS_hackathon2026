import { RecentEventsPanel } from "../components/events/RecentEventsPanel";
import { AlertsPage } from "../pages/AlertsPage";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Inbox screen (not restyled yet: renders the existing page in the legacy frame). */
export function InboxScreen({ teamId, teamLabel }: ScreenProps) {
  return (
    <PageFrame title="Inbox" context={teamLabel} isLegacy>
      <AlertsPage teamId={teamId} />
      <details className="mt-6 rounded-card border border-hairline bg-card p-4">
        <summary className="text-body font-medium">Recent events</summary>
        <div className="mt-3">
          <RecentEventsPanel />
        </div>
      </details>
    </PageFrame>
  );
}
