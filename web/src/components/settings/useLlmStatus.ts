import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { components } from "../../api/schema.gen";

export type LlmStatus = components["schemas"]["LlmStatus"];

const POLL_MS = 30_000;

/** GET /api/v1/llm/status every 30 s (the api caches its own probe for 60 s). */
export function useLlmStatus(): { status: LlmStatus | null; error: string | null } {
  const [status, setStatus] = useState<LlmStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let isCancelled = false;
    const load = async () => {
      try {
        const { data } = await apiClient.GET("/api/v1/llm/status");
        if (isCancelled) return;
        if (data) {
          setStatus(data);
          setError(null);
        } else {
          setError("Status unavailable");
        }
      } catch {
        if (!isCancelled) setError("Could not reach the API");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => {
      isCancelled = true;
      window.clearInterval(timer);
    };
  }, []);
  return { status, error };
}
