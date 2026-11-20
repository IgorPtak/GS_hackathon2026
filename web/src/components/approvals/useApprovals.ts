import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { ApprovalRequest } from "../../api/types";

interface ListState {
  readonly team: string;
  readonly items: readonly ApprovalRequest[];
  readonly error: string | null;
  readonly isLoaded: boolean;
}

/** Pending approval requests of a team; `apply` merges live requested/decided events. */
export function useApprovals(team: string) {
  const [state, setState] = useState<ListState>({
    team,
    items: [],
    error: null,
    isLoaded: false,
  });

  const teamRef = useRef(team);

  const load = useCallback(async () => {
    let next: ListState;
    try {
      const { data, response } = await apiClient.GET("/api/v1/approvals", {
        params: { query: { team, is_pending: true } },
      });
      next = data
        ? { team, items: data, error: null, isLoaded: true }
        : {
            team,
            items: [],
            error:
              response.status === 404 || response.status === 503
                ? "Approvals are not available yet"
                : `API error ${String(response.status)}`,
            isLoaded: true,
          };
    } catch (e) {
      next = {
        team,
        items: [],
        error: e instanceof Error ? e.message : "API unreachable",
        isLoaded: true,
      };
    }
    if (teamRef.current !== team) return;
    setState((prev) =>
      next.error && prev.team === team && prev.items.length > 0
        ? { ...prev, error: next.error }
        : next,
    );
  }, [team]);

  useEffect(() => {
    teamRef.current = team;
    void load();
  }, [team, load]);

  const apply = useCallback(
    (request: ApprovalRequest) => {
      if (request.team !== team) return;
      setState((prev) => {
        const others = prev.items.filter((item) => item.id !== request.id);
        const items =
          request.decision === null
            ? [...others, request].sort(
                (a, b) => Date.parse(a.requested_at) - Date.parse(b.requested_at),
              )
            : others;
        return { ...prev, items };
      });
    },
    [team],
  );

  const isCurrent = state.team === team;
  return {
    items: isCurrent ? state.items : [],
    error: isCurrent ? state.error : null,
    isLoading: !isCurrent || !state.isLoaded,
    apply,
    reload: () => {
      void load();
    },
  };
}
