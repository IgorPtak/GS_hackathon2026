import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { components } from "../../api/schema.gen";

export type MetricsSummary = components["schemas"]["MetricsSummary"];

const REFRESH_INTERVAL_MS = 5000;

interface MetricsState {
  readonly summary: MetricsSummary | null;
  readonly error: string | null;
  readonly updatedAt: Date | null;
}

/** Polls the summary every 5 s while the tab is visible. */
export function useMetricsSummary(): MetricsState {
  const [summary, setSummary] = useState<MetricsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const requestSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    try {
      const { data, error: apiError } = await apiClient.GET("/api/v1/metrics/summary");
      if (seq !== requestSeq.current) return;
      if (data) {
        setSummary(data);
        setUpdatedAt(new Date());
        setError(null);
      } else {
        setError(`API error: ${JSON.stringify(apiError)}`);
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

  return { summary, error, updatedAt };
}
