import { Card } from "../ui/Card";
import { Skeleton } from "../ui/Skeleton";
import { MetricTile } from "./MetricTile";
import type { MetricsHistory, MetricsSummary } from "./useMetricsSummary";

interface MetricsPanelProps {
  readonly summary: MetricsSummary | null;
  readonly history: MetricsHistory;
  readonly error: string | null;
}

function formatRate(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  if (value >= 100) return Math.round(value).toLocaleString();
  return value.toFixed(1);
}

function formatCount(value: number | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  return value.toLocaleString();
}

/** Latency arrives in seconds; show milliseconds below one second. */
function formatLatency(seconds: number | null | undefined): { value: string | null; unit: string } {
  if (seconds === null || seconds === undefined) return { value: null, unit: "" };
  if (seconds < 1) return { value: String(Math.round(seconds * 1000)), unit: "ms" };
  return { value: seconds.toFixed(2), unit: "s" };
}

function LoadingGrid() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Loading metrics">
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Card key={i} className="space-y-4">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-10 w-28" />
            <Skeleton className="h-8 w-full" />
          </Card>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
        {[0, 1, 2, 3, 4].map((i) => (
          <div key={i} className="space-y-3 rounded-tile border border-hairline bg-card p-4">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-7 w-16" />
            <Skeleton className="h-6 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

/** Live pipeline health: three hero numbers above five supporting queue and delivery tiles. */
export function MetricsPanel({ summary, history, error }: MetricsPanelProps) {
  if (summary === null && !error) return <LoadingGrid />;

  const throughput = summary
    ? (summary.processed_rate_per_second ?? summary.ingest_rate_per_second)
    : null;
  const ingestSub =
    summary?.ingest_rate_per_second !== null &&
    summary?.ingest_rate_per_second !== undefined &&
    summary.processed_rate_per_second !== null
      ? `Ingest ${formatRate(summary.ingest_rate_per_second) ?? "0"}/s`
      : "Processed through rules and outbox";

  const p99 = formatLatency(summary?.e2e_latency_p99_seconds);
  const p50 = formatLatency(summary?.e2e_latency_p50_seconds);
  const p50Sub =
    p50.value !== null ? `Median (p50) ${p50.value} ${p50.unit}` : "Ingest to delivery";

  const lostCount = summary ? (summary.dead_lettered_total ?? 0) : null;
  const isZeroLost = lostCount === 0;

  return (
    <div className="space-y-6">
      {error ? (
        <p
          role="alert"
          className="rounded-tile border border-warning/30 bg-warning/10 px-4 py-3 text-body text-warning-ink"
        >
          Could not refresh metrics ({error}). Retrying every 2 seconds.
        </p>
      ) : null}

      {summary ? (
        <>
          <dl className="grid grid-cols-1 gap-5 md:grid-cols-3">
            <MetricTile
              size="hero"
              label="Events per second"
              value={formatRate(throughput)}
              unit="events/s"
              sublabel={ingestSub}
              history={history.eventsPerSecond}
            />
            <MetricTile
              size="hero"
              label="p99 end-to-end latency"
              value={p99.value}
              unit={p99.unit}
              sublabel={p50Sub}
              history={history.latencyP99Ms}
            />
            <MetricTile
              size="hero"
              label="Lost messages"
              value={formatCount(lostCount)}
              tone={isZeroLost ? "success" : "critical"}
              badge={isZeroLost ? "Zero lost" : "Needs attention"}
              sublabel="Transactional outbox delivery"
              history={history.lost}
            />
          </dl>

          <section aria-labelledby="pipeline-details-heading" className="space-y-3">
            <h2 id="pipeline-details-heading" className="text-row font-semibold text-ink">
              Pipeline queues and deliveries
            </h2>
            <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
              <MetricTile
                label="Open alerts"
                value={formatCount(summary.open_alert_count)}
                history={history.openAlerts}
              />
              <MetricTile
                label="Retries"
                value={formatCount(summary.retries_total)}
                history={history.retries}
              />
              <MetricTile
                label="Dead-lettered"
                value={formatCount(summary.dead_lettered_total)}
                tone={
                  summary.dead_lettered_total !== null && summary.dead_lettered_total > 0
                    ? "critical"
                    : "default"
                }
                history={history.deadLettered}
              />
              <MetricTile
                label="Events stream lag"
                value={formatCount(summary.events_stream_lag)}
                history={history.eventsLag}
              />
              <MetricTile
                label="Deliveries lag"
                value={formatCount(summary.deliveries_stream_lag)}
                history={history.deliveriesLag}
              />
            </dl>
          </section>
        </>
      ) : null}
    </div>
  );
}
