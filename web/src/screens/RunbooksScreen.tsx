import { RunbooksPage } from "../pages/RunbooksPage";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Runbooks screen (not restyled yet: renders the existing page in the legacy frame). */
export function RunbooksScreen({ teamLabel }: ScreenProps) {
  return (
    <PageFrame title="Runbooks" context={teamLabel} isLegacy>
      <RunbooksPage />
    </PageFrame>
  );
}
