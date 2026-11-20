import { ApprovalsPage } from "../pages/ApprovalsPage";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Approvals screen (not restyled yet: renders the existing page in the legacy frame). */
export function ApprovalsScreen({ teamId, teamLabel }: ScreenProps) {
  return (
    <PageFrame title="Approvals" context={teamLabel} isLegacy>
      <ApprovalsPage teamId={teamId} />
    </PageFrame>
  );
}
