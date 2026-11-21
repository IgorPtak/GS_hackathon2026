import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { Actor, ActionRun } from "../../api/types";

/** Plain words for the run route's refusals (contract v1.1: 404, 409, 422). */
function runErrorMessage(status: number, error: unknown): string {
  const code =
    typeof error === "object" && error !== null && "error" in error ? String(error.error) : "";
  if (code === "alert_resolved")
    return "This alert is resolved, so its runbook steps no longer run.";
  if (code === "step_already_run") return "This step already has a run. Refresh to see it.";
  if (status === 422) return "This step is missing a value it needs, so it cannot run yet.";
  return `Could not run the step (API error ${String(status)}).`;
}

/** Starts a manual runbook step; `busyIndex` is the step being started, `error` the last failure. */
export function useStepRun(alertId: string, team: string, onStarted: (run: ActionRun) => void) {
  const [busyIndex, setBusyIndex] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    async (stepIndex: number) => {
      const actor: Actor = { id: `${team}-operator`, display_name: null };
      setBusyIndex(stepIndex);
      setError(null);
      try {
        const {
          data,
          error: apiError,
          response,
        } = await apiClient.POST("/api/v1/alerts/{alert_id}/runbook/steps/{step_index}/run", {
          params: { path: { alert_id: alertId, step_index: stepIndex } },
          body: { actor },
        });
        if (data) onStarted(data);
        else if (response.status === 404 || response.status === 503)
          setError("Running steps is not available yet.");
        else setError(runErrorMessage(response.status, apiError));
      } catch (e) {
        setError(`Could not run the step: ${e instanceof Error ? e.message : "API unreachable"}.`);
      } finally {
        setBusyIndex(null);
      }
    },
    [alertId, team, onStarted],
  );

  return { busyIndex, error, run };
}
