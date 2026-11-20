import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { Actor, Alert } from "../../api/types";

export type AlertTransition = "acknowledge" | "resolve";

/**
 * Acknowledge/resolve with an optimistic update: `apply` shows the new status at once and,
 * on failure, is called again with the previous alert to roll back.
 */
export function useAlertTransition(apply: (alert: Alert, isForced: boolean) => void) {
  const [pending, setPending] = useState<AlertTransition | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (alert: Alert, transition: AlertTransition) => {
      const actor: Actor = { id: `${alert.team}-operator`, display_name: null };
      const now = new Date().toISOString();
      const optimistic: Alert =
        transition === "acknowledge"
          ? { ...alert, status: "acknowledged", acknowledged_by: actor, acknowledged_at: now }
          : { ...alert, status: "resolved", resolved_by: actor, resolved_at: now };
      setPending(transition);
      setError(null);
      apply(optimistic, true);
      try {
        const path = { alert_id: alert.id };
        const { data, response } =
          transition === "acknowledge"
            ? await apiClient.POST("/api/v1/alerts/{alert_id}/acknowledge", {
                params: { path },
                body: { actor },
              })
            : await apiClient.POST("/api/v1/alerts/{alert_id}/resolve", {
                params: { path },
                body: { actor, comment: null },
              });
        if (data) {
          apply(data, true);
        } else {
          apply(alert, true);
          setError(
            response.status === 409
              ? `Cannot ${transition} this alert: it is already ${alert.status === "resolved" ? "resolved" : "in another state"}.`
              : `Could not ${transition} the alert (API error ${String(response.status)}).`,
          );
        }
      } catch (e) {
        apply(alert, true);
        setError(
          `Could not ${transition} the alert: ${e instanceof Error ? e.message : "API unreachable"}.`,
        );
      } finally {
        setPending(null);
      }
    },
    [apply],
  );

  return {
    pending,
    error,
    run,
    clearError: () => {
      setError(null);
    },
  };
}
