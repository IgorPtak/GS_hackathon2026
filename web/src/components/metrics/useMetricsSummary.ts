import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { components } from "../../api/schema.gen";

export type MetricsSummary = components["schemas"]["MetricsSummary"];

export const REFRESH_INTERVAL_MS = 2000;
const HISTORY_LIMIT = 30;

export interface MetricsHistory {
  readonly eventsPerSecond: readonly (number | null)[];
  readonly latencyP99Ms: readonly (number | null)[];
  readonly lost: readonly (number | null)[];
  readonly openAlerts: readonly (number | null)[];
  readonly retries: readonly (number | null)[];
  readonly deadLettered: readonly (number | null)[];
  readonly eventsLag: readonly (number | null)[];
  readonly deliveriesLag: readonly (number | null)[];
}

const EMPTY_HISTORY: MetricsHistory = {
  eventsPerSecond: [],
  latencyP99Ms: [],
  lost: [],
  openAlerts: [],
  retries: [],
  deadLettered: [],
  eventsLag: [],
  deliveriesLag: [],
};

function appendSample(
  series: readonly (number | null)[],
  value: number | null,
): readonly (number | null)[] {
  const next = [...series, value];
  return next.length > HISTORY_LIMIT ? next.slice(next.length - HISTORY_LIMIT) : next;
}

function appendSummary(prev: MetricsHistory, summary: MetricsSummary): MetricsHistory {
  const rate = summary.processed_rate_per_second ?? summary.ingest_rate_per_second;
  const p99Ms =
    summary.e2e_latency_p99_seconds === null ? null : summary.e2e_latency_p99_seconds * 1000;
  const lost = summary.dead_lettered_total ?? 0;
  return {
    eventsPerSecond: appendSample(prev.eventsPerSecond, rate),
    latencyP99Ms: appendSample(prev.latencyP99Ms, p99Ms),
    lost: appendSample(prev.lost, lost),
    openAlerts: appendSample(prev.openAlerts, summary.open_alert_count),
    retries: appendSample(prev.retries, summary.retries_total),
    deadLettered: appendSample(prev.deadLettered, summary.dead_lettered_total),
    eventsLag: appendSample(prev.eventsLag, summary.events_stream_lag),
    deliveriesLag: appendSample(prev.deliveriesLag, summary.deliveries_stream_lag),
  };
}

export interface MetricsState {
  readonly summary: MetricsSummary | null;
  readonly history: MetricsHistory;
  readonly error: string | null;
  readonly updatedAt: Date | null;
}

/** Polls GET /api/v1/metrics/summary every 2 s while the tab is visible and keeps client history. */
export function useMetricsSummary(): MetricsState {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [history, setHistory] = useState<MetricsHistory>(EMPTY_HISTORY);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const requestSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    try {
      const { data, response } = await apiClient.GET("/api/v1/metrics/summary");
      if (seq !== requestSeq.current) return;
      if (data) {
        setSummary(data);
        setHistory((prev) => appendSummary(prev, data));
        setUpdatedAt(new Date());
        setError(null);
      } else {
        setError(`Metrics request returned ${String(response.status)}`);
      }
    } catch (e) {
      if (seq !== requestSeq.current) return;
      setError(e instanceof Error ? e.message : "API unreachable");
    }
  }, []);

  useEffect(() => {
    let timer: number | undefined;
    const stop = () => {
      if (timer !== undefined) {
        window.clearInterval(timer);
        timer = undefined;
      }
    };
    const start = () => {
      stop();
      void load();
      timer = window.setInterval(() => void load(), REFRESH_INTERVAL_MS);
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };
    if (!document.hidden) start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
      requestSeq.current += 1;
    };
  }, [load]);

  return { summary, history, error, updatedAt };
}
