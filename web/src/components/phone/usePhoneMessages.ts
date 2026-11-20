import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { PhoneMessage } from "../../api/types";

interface MessagesState {
  readonly recipientId: string | null;
  readonly items: readonly PhoneMessage[];
  readonly error: string | null;
  readonly isLoaded: boolean;
}

function byTime(a: PhoneMessage, b: PhoneMessage): number {
  return Date.parse(a.at) - Date.parse(b.at) || a.id.localeCompare(b.id);
}

/** Messages of one recipient, oldest first; `apply` merges live `phone.message` events. */
export function usePhoneMessages(recipientId: string | null) {
  const [state, setState] = useState<MessagesState>({
    recipientId,
    items: [],
    error: null,
    isLoaded: false,
  });

  const idRef = useRef(recipientId);

  const load = useCallback(async () => {
    if (recipientId === null) return;
    let next: MessagesState;
    try {
      const { data, response } = await apiClient.GET("/api/v1/phone-simulator/messages", {
        params: { query: { recipient_id: recipientId } },
      });
      next = data
        ? { recipientId, items: [...data].sort(byTime), error: null, isLoaded: true }
        : {
            recipientId,
            items: [],
            error:
              response.status === 404 || response.status === 503
                ? "Phone simulator is not available yet"
                : `API error ${String(response.status)}`,
            isLoaded: true,
          };
    } catch (e) {
      next = {
        recipientId,
        items: [],
        error: e instanceof Error ? e.message : "API unreachable",
        isLoaded: true,
      };
    }
    if (idRef.current !== recipientId) return;
    setState((prev) =>
      next.error && prev.recipientId === recipientId && prev.items.length > 0
        ? { ...prev, error: next.error }
        : next,
    );
  }, [recipientId]);

  useEffect(() => {
    idRef.current = recipientId;
    void load();
  }, [recipientId, load]);

  const apply = useCallback(
    (message: PhoneMessage) => {
      if (message.recipient_id !== recipientId) return;
      setState((prev) =>
        prev.recipientId !== recipientId || prev.items.some((item) => item.id === message.id)
          ? prev
          : { ...prev, items: [...prev.items, message].sort(byTime) },
      );
    },
    [recipientId],
  );

  const isCurrent = state.recipientId === recipientId;
  return {
    messages: isCurrent ? state.items : [],
    error: isCurrent ? state.error : null,
    isLoading: recipientId !== null && (!isCurrent || !state.isLoaded),
    apply,
    reload: () => {
      void load();
    },
  };
}
