import { MetricsPanel } from "../components/metrics/MetricsPanel";
import { useMetricsSummary } from "../components/metrics/useMetricsSummary";
import { Icon } from "../components/ui/icons";
import { PageFrame } from "../components/ui/PageFrame";
import { DemoSheet } from "./DemoScreen";
import type { ScreenProps } from "./types";

const GRAFANA_URL = "http://localhost:3000";

/** Live pipeline health and throughput insights, polled every 2 s. */
export function InsightsScreen({ onNavigate }: ScreenProps) {
  const { summary, history, error, updatedAt } = useMetricsSummary();
  const context = updatedAt
    ? `Live · updated ${updatedAt.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`
    : "Live · polling every 2 s";

  return (
    <>
      <PageFrame
        title="Insights"
        context={context}
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
        <MetricsPanel summary={summary} history={history} error={error} />
      </PageFrame>
      <DemoSheet onNavigate={onNavigate} />
    </>
  );
}
