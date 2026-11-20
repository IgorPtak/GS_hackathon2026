import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { RunbookStep } from "../../api/types";

interface Loaded {
  readonly id: string;
  readonly steps: readonly RunbookStep[] | null;
  readonly error: string | null;
}

/** Current steps of a runbook; null id means "no runbook". */
export function useRunbookSteps(runbookId: string | null) {
  const [state, setState] = useState<Loaded | null>(null);
  useEffect(() => {
    if (runbookId === null) return;
    let isCancelled = false;
    apiClient
      .GET("/api/v1/runbooks/{runbook_id}", { params: { path: { runbook_id: runbookId } } })
      .then(({ data, response }) => {
        if (isCancelled) return;
        setState({
          id: runbookId,
          steps: data ? data.steps : null,
          error: data ? null : `Cannot load runbook (API error ${String(response.status)})`,
        });
      })
      .catch((e: unknown) => {
        if (!isCancelled)
          setState({
            id: runbookId,
            steps: null,
            error: e instanceof Error ? e.message : "API unreachable",
          });
      });
    return () => {
      isCancelled = true;
    };
  }, [runbookId]);
  const own = runbookId !== null && state?.id === runbookId ? state : null;
  return {
    steps: own?.steps ?? null,
    error: own?.error ?? null,
    isLoading: runbookId !== null && own === null,
  };
}
