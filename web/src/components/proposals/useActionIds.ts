import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";

let cached: readonly string[] | null = null;

/** Action ids from GET /config (empty while loading or when unavailable). */
export function useActionIds(): readonly string[] {
  const [ids, setIds] = useState<readonly string[]>(cached ?? []);
  useEffect(() => {
    if (cached) return;
    let isCancelled = false;
    apiClient
      .GET("/api/v1/config")
      .then(({ data }) => {
        if (!data) return;
        cached = data.actions.map((action) => action.id);
        if (!isCancelled) setIds(cached);
      })
      .catch(() => {
        // The action id stays optional; the select simply has no options.
      });
    return () => {
      isCancelled = true;
    };
  }, []);
  return ids;
}
