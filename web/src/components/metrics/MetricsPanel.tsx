import { MetricTile } from "./MetricTile";
import { useMetricsSummary } from "./useMetricsSummary";

const GRAFANA_URL = "http://localhost:3000";
const MISSING = "—";

function formatNumber(value: number | null | undefined, digits: number): string {
  return value === null || value === undefined ? MISSING : value.toFixed(digits);
}

function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined ? MISSING : value.toLocaleString();
}

/** Latency arrives in seconds; show milliseconds below one second. */
function formatLatency(seconds: number | null | undefined): { value: string; unit: string } {
  if (seconds === null || seconds === undefined) return { value: MISSING, unit: "" };
  if (seconds < 1) return { value: (seconds * 1000).toFixed(0), unit: "ms" };
  return { value: seconds.toFixed(2), unit: "s" };
}

export function MetricsPanel() {
  const { summary, error, updatedAt } = useMetricsSummary();
  const p50 = formatLatency(summary?.e2e_latency_p50_seconds);
  const p99 = formatLatency(summary?.e2e_latency_p99_seconds);

  return (
    <section className="rounded border border-slate-200 bg-slate-50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Metrics</h2>
        <div className="flex items-center gap-4 text-sm text-slate-600">
          <span>{updatedAt ? `Updated ${updatedAt.toLocaleTimeString()}` : "Not updated yet"}</span>
          <a
            href={GRAFANA_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-700 underline"
          >
            Open Grafana
          </a>
        </div>
      </div>
      {error ? (
        <p role="alert" className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Cannot load metrics ({error}). Retrying every 5 s.
        </p>
      ) : null}
      {summary === null ? (
        error ? null : (
          <p className="mt-3 text-sm text-slate-500">Loading metrics...</p>
        )
      ) : (
        <dl className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          <MetricTile
            label="Ingest rate"
            value={formatNumber(summary.ingest_rate_per_second, 1)}
            unit="msg/s"
          />
          <MetricTile
            label="Processed rate"
            value={formatNumber(summary.processed_rate_per_second, 1)}
            unit="msg/s"
          />
          <MetricTile
            label="Events stream lag"
            value={formatCount(summary.events_stream_lag)}
            unit="entries"
          />
          <MetricTile
            label="Deliveries stream lag"
            value={formatCount(summary.deliveries_stream_lag)}
            unit="entries"
          />
          <MetricTile label="End-to-end latency p50" value={p50.value} unit={p50.unit} />
          <MetricTile label="End-to-end latency p99" value={p99.value} unit={p99.unit} />
          <MetricTile
            label="Delivery retries"
            value={formatCount(summary.retries_total)}
            unit="total"
          />
          <MetricTile
            label="Dead-lettered"
            value={formatCount(summary.dead_lettered_total)}
            unit="total"
          />
          <MetricTile
            label="Open alerts"
            value={formatCount(summary.open_alert_count)}
            unit="alerts"
          />
        </dl>
      )}
    </section>
  );
}
