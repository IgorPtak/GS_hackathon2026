import { useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { PulseSample } from "../ui/PulseBars";

const POLL_INTERVAL_MS = 2000;
const TICK_INTERVAL_MS = 1000;
const HISTORY_LENGTH = 60;

export interface PipelineMetrics {
  /** Events processed per second for the last 60 s, newest last. */
  readonly samples: readonly PulseSample[];
  readonly rate: number | null;
  readonly p99Milliseconds: number | null;
  readonly lostTotal: number | null;
  readonly hasError: boolean;
}

interface Latest {
  rate: number | null;
  p99Milliseconds: number | null;
  lostTotal: number | null;
}

/**
 * Polls the metrics summary every 2 s and records one sample per second, so the bars read as
 * seconds even though the API is only asked every other second. Both timers stop while hidden.
 */
export function usePipelineMetrics(): PipelineMetrics {
  const [metrics, setMetrics] = useState<PipelineMetrics>({
    samples: [],
    rate: null,
    p99Milliseconds: null,
    lostTotal: null,
    hasError: false,
  });
  const latest = useRef<Latest>({ rate: null, p99Milliseconds: null, lostTotal: null });
  const lostAtLastTick = useRef<number | null>(null);

  useEffect(() => {
    let pollTimer: number | undefined;
    let tickTimer: number | undefined;
    let isCancelled = false;

    const poll = async () => {
      try {
        const { data } = await apiClient.GET("/api/v1/metrics/summary");
        if (isCancelled) return;
        if (!data) {
          setMetrics((prev) => ({ ...prev, hasError: true }));
          return;
        }
        latest.current = {
          rate: data.processed_rate_per_second,
          p99Milliseconds:
            data.e2e_latency_p99_seconds === null ? null : data.e2e_latency_p99_seconds * 1000,
          lostTotal: data.dead_lettered_total,
        };
        setMetrics((prev) => ({ ...prev, ...latest.current, hasError: false }));
      } catch {
        if (!isCancelled) setMetrics((prev) => ({ ...prev, hasError: true }));
      }
    };

    const tick = () => {
      const { rate, lostTotal } = latest.current;
      const hasLoss =
        lostTotal !== null && lostAtLastTick.current !== null && lostTotal > lostAtLastTick.current;
      lostAtLastTick.current = lostTotal;
      setMetrics((prev) => ({
        ...prev,
        samples: [...prev.samples, { rate: rate ?? 0, hasLoss }].slice(-HISTORY_LENGTH),
      }));
    };

    const stop = () => {
      window.clearInterval(pollTimer);
      window.clearInterval(tickTimer);
      pollTimer = undefined;
      tickTimer = undefined;
    };
    const start = () => {
      stop();
      void poll();
      pollTimer = window.setInterval(() => void poll(), POLL_INTERVAL_MS);
      tickTimer = window.setInterval(tick, TICK_INTERVAL_MS);
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") start();
      else stop();
    };

    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      isCancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
    };
  }, []);

  return metrics;
}
