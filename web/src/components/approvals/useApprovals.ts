import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { ApprovalRequest } from "../../api/types";

interface ListState {
  readonly team: string;
  readonly items: readonly ApprovalRequest[];
  readonly decided: readonly ApprovalRequest[];
  readonly error: string | null;
  readonly isLoaded: boolean;
}

function sortPending(items: readonly ApprovalRequest[]): readonly ApprovalRequest[] {
  return [...items].sort((a, b) => Date.parse(a.requested_at) - Date.parse(b.requested_at));
}

function sortDecided(items: readonly ApprovalRequest[]): readonly ApprovalRequest[] {
  return [...items].sort(
    (a, b) =>
      Date.parse(b.decided_at ?? b.requested_at) - Date.parse(a.decided_at ?? a.requested_at),
  );
}

/** Pending and recent decided approvals for a team; `apply` merges live SSE events. */
export function useApprovals(team: string) {
  const [state, setState] = useState<ListState>({
    team,
    items: [],
    decided: [],
    error: null,
    isLoaded: false,
  });

  const teamRef = useRef(team);

  const load = useCallback(async () => {
    let next: ListState;
    try {
      const [pendingRes, decidedRes] = await Promise.all([
        apiClient.GET("/api/v1/approvals", { params: { query: { team, is_pending: true } } }),
        apiClient.GET("/api/v1/approvals", { params: { query: { team, is_pending: false } } }),
      ]);
      if (pendingRes.data) {
        next = {
          team,
          items: sortPending(pendingRes.data),
          decided: sortDecided(decidedRes.data ?? []),
          error: null,
          isLoaded: true,
        };
      } else {
        const status = pendingRes.response.status;
        next = {
          team,
          items: [],
          decided: [],
          error:
            status === 404 || status === 503
              ? "Approvals are not available yet"
              : `API error ${String(status)}`,
          isLoaded: true,
        };
      }
    } catch (e) {
      next = {
        team,
        items: [],
        decided: [],
        error: e instanceof Error ? e.message : "API unreachable",
        isLoaded: true,
      };
    }
    if (teamRef.current !== team) return;
    setState((prev) =>
      next.error && prev.team === team && (prev.items.length > 0 || prev.decided.length > 0)
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
        const nextPending = prev.items.filter((item) => item.id !== request.id);
        const nextDecided = prev.decided.filter((item) => item.id !== request.id);
        return {
          ...prev,
          items: request.decision === null ? sortPending([...nextPending, request]) : nextPending,
          decided: request.decision !== null ? sortDecided([request, ...nextDecided]) : nextDecided,
        };
      });
    },
    [team],
  );

  const isCurrent = state.team === team;
  return {
    items: isCurrent ? state.items : [],
    decided: isCurrent ? state.decided : [],
    error: isCurrent ? state.error : null,
    isLoading: !isCurrent || !state.isLoaded,
    apply,
    reload: () => {
      void load();
    },
  };
}
