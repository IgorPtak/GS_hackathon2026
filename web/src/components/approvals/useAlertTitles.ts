import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";

const alertTitleCache = new Map<string, string>();
const runbookTitleCache = new Map<string, string>();

/** Turns a kebab-case id like `workflow-failed` into `Workflow failed`. */
export function humanizeId(id: string): string {
  const words = id.replace(/[-_]+/g, " ").trim();
  if (!words) return id;
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Resolves human alert titles and runbook titles for approval and proposal cards. */
export function useApprovalContextTitles(team: string, alertIds: readonly string[]) {
  const [, setVersion] = useState(0);
  const idsKey = [...new Set(alertIds)].sort().join(",");

  useEffect(() => {
    let isCancelled = false;
    const bump = () => {
      if (!isCancelled) setVersion((v) => v + 1);
    };

    void Promise.all([
      apiClient.GET("/api/v1/alerts", { params: { query: { team, limit: 200 } } }),
      apiClient.GET("/api/v1/runbooks"),
    ])
      .then(([alertsRes, runbooksRes]) => {
        let changed = false;
        for (const alert of alertsRes.data?.items ?? []) {
          if (alertTitleCache.get(alert.id) !== alert.title) {
            alertTitleCache.set(alert.id, alert.title);
            changed = true;
          }
        }
        for (const rb of runbooksRes.data ?? []) {
          if (runbookTitleCache.get(rb.id) !== rb.title) {
            runbookTitleCache.set(rb.id, rb.title);
            changed = true;
          }
        }
        if (changed) bump();
      })
      .catch(() => {
        // Fallback labels remain visible if lookup fails.
      });

    return () => {
      isCancelled = true;
    };
  }, [team]);

  useEffect(() => {
    const missing = idsKey.split(",").filter((id) => id !== "" && !alertTitleCache.has(id));
    if (missing.length === 0) return;

    let isCancelled = false;
    void Promise.all(
      missing.map((alertId) =>
        apiClient
          .GET("/api/v1/alerts/{alert_id}", { params: { path: { alert_id: alertId } } })
          .then(({ data }) => {
            if (data) alertTitleCache.set(alertId, data.alert.title);
          })
          .catch(() => {
            // Keep fallback title when alert cannot be loaded.
          }),
      ),
    ).then(() => {
      if (!isCancelled) setVersion((v) => v + 1);
    });

    return () => {
      isCancelled = true;
    };
  }, [idsKey]);

  return {
    getAlertTitle: (alertId: string): string =>
      alertTitleCache.get(alertId) ?? `Alert ${alertId.slice(0, 8)}`,
    getRunbookTitle: (runbookId: string): string =>
      runbookTitleCache.get(runbookId) ?? humanizeId(runbookId),
  };
}
