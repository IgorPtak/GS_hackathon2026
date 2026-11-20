import { RunbooksPage } from "../pages/RunbooksPage";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Runbooks: what responders do, step by step, and how to add a new runbook. */
export function RunbooksScreen({ teamId, teamLabel }: ScreenProps) {
  return (
    <PageFrame title="Runbooks" context={teamLabel}>
      <RunbooksPage teamId={teamId} />
    </PageFrame>
  );
}
