import { useCallback, useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { RuleRecord } from "../../api/types";

interface Loaded {
  readonly team: string | null;
  readonly nonce: number;
  readonly rules: RuleRecord[];
  readonly error: string | null;
}

/** Rules of the picked team (the API may ignore the filter, so it is also applied client-side). */
export function useRules(team: string | null) {
  const [nonce, setNonce] = useState(0);
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  useEffect(() => {
    let isCancelled = false;
    const query = team === null ? {} : { team };
    apiClient
      .GET("/api/v1/rules", { params: { query } })
      .then(({ data, response }) => {
        if (isCancelled) return;
        const rules = data ? (team === null ? data : data.filter((r) => r.rule.team === team)) : [];
        setLoaded({
          team,
          nonce,
          rules,
          error: data ? null : `API error ${String(response.status)}`,
        });
      })
      .catch((e: unknown) => {
        if (isCancelled) return;
        setLoaded({
          team,
          nonce,
          rules: [],
          error: e instanceof Error ? e.message : "API unreachable",
        });
      });
    return () => {
      isCancelled = true;
    };
  }, [team, nonce]);

  const reload = useCallback(() => {
    setNonce((n) => n + 1);
  }, []);
  const isCurrent = loaded?.team === team && loaded.nonce === nonce;
  const shown = loaded?.team === team ? loaded : null;
  return {
    rules: shown?.rules ?? [],
    isLoading: !isCurrent && shown === null,
    error: shown?.error ?? null,
    reload,
  };
}
