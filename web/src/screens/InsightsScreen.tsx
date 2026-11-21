import { IllustratedBanner } from "../components/ui/IllustratedBanner";
import { MetricsPanel } from "../components/metrics/MetricsPanel";
import { useMetricsSummary } from "../components/metrics/useMetricsSummary";
import { Icon } from "../components/ui/icons";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

const GRAFANA_URL = "http://localhost:3000";

/** Live pipeline health and throughput insights, polled every 2 s. */
export function InsightsScreen({ teamLabel }: ScreenProps) {
  const { summary, history, error } = useMetricsSummary();

  return (
    <PageFrame
      title="Insights"
      context={teamLabel}
      actions={
        <a
          href={GRAFANA_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-9 shrink-0 items-center justify-center gap-2 rounded-full bg-fill px-4 text-body font-medium whitespace-nowrap text-ink transition-colors hover:bg-hairline"
        >
          <Icon name="external" size={16} />
          Open Grafana
        </a>
      }
    >
      <div className="space-y-6">
        <IllustratedBanner scene="insights" title="How Beacon is doing" focus="80% 50%">
          Live numbers from the pipeline. Nothing here needs your attention unless it turns red.
        </IllustratedBanner>
        <MetricsPanel summary={summary} history={history} error={error} />
      </div>
    </PageFrame>
  );
}
