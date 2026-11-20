import { SchemasPage } from "../pages/SchemasPage";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Connect a system screen (not restyled yet: renders the existing page in the legacy frame). */
export function ConnectScreen({ teamId, teamLabel, onNavigate }: ScreenProps) {
  return (
    <PageFrame title="Connect a system" context={teamLabel} isLegacy>
      <SchemasPage teamId={teamId} onNavigate={onNavigate} />
    </PageFrame>
  );
}
