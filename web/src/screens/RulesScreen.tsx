import { RulesPage } from "../pages/RulesPage";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Rules screen (not restyled yet: renders the existing page in the legacy frame). */
export function RulesScreen({ teamId, teamLabel }: ScreenProps) {
  return (
    <PageFrame title="Rules" context={teamLabel} isLegacy>
      <RulesPage teamId={teamId} />
    </PageFrame>
  );
}
