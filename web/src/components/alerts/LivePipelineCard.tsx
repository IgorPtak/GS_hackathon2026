import { Avatar } from "../ui/Avatar";
import { Card } from "../ui/Card";
import { PulseBars } from "../ui/PulseBars";
import { StatusChip } from "../ui/StatusChip";
import { usePipelineMetrics } from "./usePipelineMetrics";

const GRAFANA_URL = "http://localhost:3000";

function formatRate(rate: number | null): string {
  if (rate === null) return "–";
  return rate >= 10 ? Math.round(rate).toString() : rate.toFixed(1);
}

function formatMilliseconds(value: number | null): string {
  return value === null ? "–" : Math.round(value).toString();
}

/** The one bold spot of the Inbox: live throughput bars, latency and the "0 lost" promise. */
export function LivePipelineCard({ teamId, teamLabel }: { teamId: string; teamLabel: string }) {
  const metrics = usePipelineMetrics();
  const lost = metrics.lostTotal;
  return (
    <Card className="flex flex-wrap items-center gap-x-8 gap-y-4 @container">
      <div className="flex items-center gap-4">
        <Avatar name={teamLabel} team={teamId} size="xl" />
        <div>
          <h2 className="text-row font-semibold">Live pipeline</h2>
          <p className="num text-meta text-ink-2" aria-live="off">
            {formatRate(metrics.rate)} events/s · p99 {formatMilliseconds(metrics.p99Milliseconds)}{" "}
            ms
          </p>
        </div>
      </div>
      <PulseBars samples={metrics.samples} className="min-w-40 flex-1" />
      <div className="flex items-center gap-3">
        {metrics.hasError ? (
          <StatusChip tone="warning">Metrics unavailable</StatusChip>
        ) : lost === null ? (
          <StatusChip>Counting</StatusChip>
        ) : lost > 0 ? (
          <StatusChip tone="critical" icon="alert">
            {lost.toLocaleString()} lost
          </StatusChip>
        ) : (
          <StatusChip tone="success" icon="check">
            0 lost
          </StatusChip>
        )}
        <a
          href={GRAFANA_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex h-9 items-center rounded-full px-3 text-meta font-medium text-ink-2 transition-colors hover:bg-fill hover:text-ink"
        >
          Open Grafana
        </a>
      </div>
    </Card>
  );
}
