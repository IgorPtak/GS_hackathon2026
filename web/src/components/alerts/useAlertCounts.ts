import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { AlertStatus } from "../../api/types";

export type AlertCounts = Readonly<Record<AlertStatus, number>>;

const STATUSES: readonly AlertStatus[] = ["open", "acknowledged", "resolved"];
/** Counts are capped by one page; an inbox with more than this is not a calm inbox anyway. */
const COUNT_LIMIT = 200;
const REFRESH_DEBOUNCE_MS = 800;

async function fetchCounts(team: string): Promise<AlertCounts | null> {
  try {
    const pages = await Promise.all(
      STATUSES.map((status) =>
        apiClient.GET("/api/v1/alerts", {
          params: { query: { team, status, limit: COUNT_LIMIT } },
        }),
      ),
    );
    if (pages.some((page) => !page.data)) return null;
    const [open, acknowledged, resolved] = pages.map((page) => page.data?.items.length ?? 0);
    return { open: open ?? 0, acknowledged: acknowledged ?? 0, resolved: resolved ?? 0 };
  } catch {
    // Counts are decoration; the list itself reports load errors.
    return null;
  }
}

/** Per-status alert counts for the filter pills; `refresh` is debounced for bursts of SSE events. */
export function useAlertCounts(team: string) {
  const [counts, setCounts] = useState<AlertCounts | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let isCancelled = false;
    void fetchCounts(team).then((result) => {
      if (!isCancelled && result) setCounts(result);
    });
    return () => {
      isCancelled = true;
    };
  }, [team, reloadToken]);

  useEffect(
    () => () => {
      window.clearTimeout(timer.current);
    },
    [],
  );

  const refresh = useCallback(() => {
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setReloadToken((token) => token + 1);
    }, REFRESH_DEBOUNCE_MS);
  }, []);

  return { counts, refresh };
}
