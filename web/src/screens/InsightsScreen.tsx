import { MetricsPanel } from "../components/metrics/MetricsPanel";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Insights screen (not restyled yet: renders the existing page in the legacy frame). */
export function InsightsScreen({ teamLabel }: ScreenProps) {
  return (
    <PageFrame title="Insights" context={teamLabel} isLegacy>
      <MetricsPanel />
    </PageFrame>
  );
}
