import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { components } from "../../api/schema.gen";

export type ChannelHealth = components["schemas"]["ChannelHealth"];

const REFRESH_MS = 3000;

/** GET /api/v1/channels/health every few seconds while the tab is visible. */
export function useChannelHealth(): {
  readonly channels: readonly ChannelHealth[] | null;
  readonly error: string | null;
} {
  const [channels, setChannels] = useState<readonly ChannelHealth[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;
    const load = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const { data } = await apiClient.GET("/api/v1/channels/health");
        if (isCancelled) return;
        if (data) {
          setChannels(data);
          setError(null);
        } else {
          setError("Could not read channel health");
        }
      } catch {
        if (!isCancelled) setError("Cannot reach the API");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), REFRESH_MS);
    return () => {
      isCancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return { channels, error };
}
