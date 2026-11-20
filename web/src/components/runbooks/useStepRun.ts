import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { Actor, ActionRun } from "../../api/types";

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
        const { data, response } = await apiClient.POST(
          "/api/v1/alerts/{alert_id}/runbook/steps/{step_index}/run",
          { params: { path: { alert_id: alertId, step_index: stepIndex } }, body: { actor } },
        );
        if (data) onStarted(data);
        else if (response.status === 404 || response.status === 503)
          setError("Running steps is not available yet.");
        else setError(`Could not run the step (API error ${String(response.status)}).`);
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
