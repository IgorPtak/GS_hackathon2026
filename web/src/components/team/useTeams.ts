import { useCallback, useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { Team } from "../../api/types";

interface TeamsState {
  readonly teams: readonly Team[];
  readonly isLoading: boolean;
  readonly error: string | null;
}

/** Teams from GET /api/v1/config, loaded once on mount; `reload` retries after a failure. */
export function useTeams(): TeamsState & { reload: () => void } {
  const [state, setState] = useState<TeamsState>({ teams: [], isLoading: true, error: null });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let isCancelled = false;
    async function load() {
      try {
        const { data } = await apiClient.GET("/api/v1/config");
        if (isCancelled) return;
        setState(
          data
            ? { teams: data.teams, isLoading: false, error: null }
            : { teams: [], isLoading: false, error: "Could not load teams" },
        );
      } catch {
        if (!isCancelled) {
          setState({ teams: [], isLoading: false, error: "Could not reach the API" });
        }
      }
    }
    void load();
    return () => {
      isCancelled = true;
    };
  }, [attempt]);

  const reload = useCallback(() => {
    setState((current) => ({ ...current, isLoading: true, error: null }));
    setAttempt((value) => value + 1);
  }, []);

  return { ...state, reload };
}
