import { PageFrame } from "../components/ui/PageFrame";
import { ApprovalsPage } from "../pages/ApprovalsPage";
import type { ScreenProps } from "./types";

/** Approvals screen: runbook approval requests, recent decisions and fix proposals. */
export function ApprovalsScreen({ teamId, teamLabel, onNavigate }: ScreenProps) {
  return (
    <PageFrame title="Approvals" context={teamLabel}>
      <ApprovalsPage teamId={teamId} onNavigate={onNavigate} />
    </PageFrame>
  );
}
