import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { Alert } from "../../api/types";
import type { components } from "../../api/schema.gen";

type ApprovalRequest = components["schemas"]["ApprovalRequest"];

export interface HomeSummary {
  readonly openAlerts: readonly Alert[];
  readonly openAlertTotal: number | null;
  readonly approvals: readonly ApprovalRequest[];
  readonly ruleCount: number | null;
  readonly runbookCount: number | null;
}

const EMPTY: HomeSummary = {
  openAlerts: [],
  openAlertTotal: null,
  approvals: [],
  ruleCount: null,
  runbookCount: null,
};
const REFRESH_MS = 10_000;

async function load(team: string): Promise<HomeSummary> {
  const [alerts, approvals, rules, runbooks] = await Promise.all([
    apiClient.GET("/api/v1/alerts", { params: { query: { team, status: "open", limit: 50 } } }),
    apiClient.GET("/api/v1/approvals", { params: { query: { team, is_pending: true } } }),
    apiClient.GET("/api/v1/rules", { params: { query: { team } } }),
    apiClient.GET("/api/v1/runbooks"),
  ]);
  const items = alerts.data?.items ?? [];
  return {
    openAlerts: items.slice(0, 3),
    openAlertTotal: alerts.data ? items.length : null,
    approvals: approvals.data ?? [],
    ruleCount: rules.data?.length ?? null,
    runbookCount: runbooks.data?.filter((r) => r.team === team || r.team === null).length ?? null,
  };
}

/** The small numbers the home page shows, refreshed every 10 s. */
export function useHomeSummary(team: string): HomeSummary {
  const [summary, setSummary] = useState<HomeSummary>(EMPTY);
  useEffect(() => {
    let isCancelled = false;
    const refresh = () => {
      load(team)
        .then((next) => {
          if (!isCancelled) setSummary(next);
        })
        .catch(() => undefined);
    };
    refresh();
    const timer = window.setInterval(refresh, REFRESH_MS);
    return () => {
      isCancelled = true;
      window.clearInterval(timer);
    };
  }, [team]);
  return summary;
}
