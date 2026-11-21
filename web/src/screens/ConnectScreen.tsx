import { SchemasPage } from "../pages/SchemasPage";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Connect a system: teach Beacon a new event shape in three steps. */
export function ConnectScreen({ teamId, teamLabel, onNavigate }: ScreenProps) {
  return (
    <PageFrame title="Connect a system" context={teamLabel}>
      <SchemasPage teamId={teamId} onNavigate={onNavigate} />
    </PageFrame>
  );
}
