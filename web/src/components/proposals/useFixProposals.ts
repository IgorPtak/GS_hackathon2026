import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { FixProposal } from "../../api/types";

interface ListState {
  readonly key: string;
  readonly items: readonly FixProposal[];
  readonly error: string | null;
  readonly isLoaded: boolean;
}

/** Fix proposals owned by a team: pending only, or all decided ones too. `apply` merges SSE updates. */
export function useFixProposals(team: string, isShowingDecided: boolean) {
  const key = `${team}:${String(isShowingDecided)}`;
  const [state, setState] = useState<ListState>({ key, items: [], error: null, isLoaded: false });
  const keyRef = useRef(key);

  const load = useCallback(async () => {
    let next: ListState;
    try {
      const { data, response } = await apiClient.GET("/api/v1/fix-proposals", {
        params: { query: isShowingDecided ? { team } : { team, status: "pending" } },
      });
      next = data
        ? { key, items: data, error: null, isLoaded: true }
        : { key, items: [], error: `API error ${String(response.status)}`, isLoaded: true };
    } catch (e) {
      next = {
        key,
        items: [],
        error: e instanceof Error ? e.message : "API unreachable",
        isLoaded: true,
      };
    }
    if (keyRef.current !== key) return;
    setState((prev) =>
      next.error && prev.key === key && prev.items.length > 0
        ? { ...prev, error: next.error }
        : next,
    );
  }, [team, isShowingDecided, key]);

  useEffect(() => {
    keyRef.current = key;
    void load();
  }, [key, load]);

  const apply = useCallback(
    (proposal: FixProposal) => {
      if (proposal.owner_team !== team) return;
      setState((prev) => {
        const others = prev.items.filter((item) => item.id !== proposal.id);
        const isListed = isShowingDecided || proposal.status === "pending";
        const items = isListed
          ? [...others, proposal].sort(
              (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
            )
          : others;
        return { ...prev, items };
      });
    },
    [team, isShowingDecided],
  );

  const isCurrent = state.key === key;
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
