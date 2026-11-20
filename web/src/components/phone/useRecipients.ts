import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { Recipient } from "../../api/types";

/** All recipients from GET /api/v1/config (every team: phone.message is broadcast). */
export function useRecipients() {
  const [recipients, setRecipients] = useState<readonly Recipient[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;
    async function load() {
      try {
        const { data, response } = await apiClient.GET("/api/v1/config");
        if (isCancelled) return;
        if (data) setRecipients(data.recipients);
        else setError(`API error ${String(response.status)}`);
      } catch (e) {
        if (!isCancelled) setError(e instanceof Error ? e.message : "API unreachable");
      }
    }
    void load();
    return () => {
      isCancelled = true;
    };
  }, []);

  return { recipients: recipients ?? [], isLoading: recipients === null && error === null, error };
}
