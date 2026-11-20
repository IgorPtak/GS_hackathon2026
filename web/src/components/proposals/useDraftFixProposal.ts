import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { FixProposalCreate } from "../../api/types";
import { messageFromBody } from "../rules/ruleErrors";

const UNAVAILABLE_MESSAGE =
  "AI drafting is unavailable right now. You can still write the fix yourself below.";

/** POST /alerts/{id}/fix-proposals/draft; the draft is never saved, only used to prefill a form. */
export function useDraftFixProposal(alertId: string) {
  const [isDrafting, setIsDrafting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const draft = useCallback(async (): Promise<FixProposalCreate | null> => {
    setIsDrafting(true);
    setMessage(null);
    try {
      const { data, error, response } = await apiClient.POST(
        "/api/v1/alerts/{alert_id}/fix-proposals/draft",
        { params: { path: { alert_id: alertId } } },
      );
      if (data) return data;
      setMessage(
        response.status === 503
          ? UNAVAILABLE_MESSAGE
          : messageFromBody(
              error,
              `Could not draft a fix (API error ${String(response.status)}). Write one below instead.`,
            ),
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not reach the server. Try again.");
    } finally {
      setIsDrafting(false);
    }
    return null;
  }, [alertId]);

  return { isDrafting, message, draft };
}
