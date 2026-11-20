import { useCallback, useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { ConfigLists } from "../../api/types";

/** GET /api/v1/config with a reload (used after a preference save to pick up the new version). */
export function useConfigLists() {
  const [nonce, setNonce] = useState(0);
  const [config, setConfig] = useState<ConfigLists | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;
    apiClient
      .GET("/api/v1/config")
      .then(({ data, response }) => {
        if (isCancelled) return;
        if (data) {
          setConfig(data);
          setError(null);
        } else setError(`API error ${String(response.status)}`);
      })
      .catch((e: unknown) => {
        if (!isCancelled) setError(e instanceof Error ? e.message : "API unreachable");
      });
    return () => {
      isCancelled = true;
    };
  }, [nonce]);

  const reload = useCallback(() => {
    setNonce((n) => n + 1);
  }, []);
  return { config, error, isLoading: config === null && error === null, reload };
}
