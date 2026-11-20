import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { FixProposalCreate } from "../../api/types";
import { messageFromBody } from "../rules/ruleErrors";

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
        messageFromBody(
          error,
          response.status === 503
            ? "LLM unavailable"
            : `Could not draft a proposal (API error ${String(response.status)})`,
        ),
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "API unreachable");
    } finally {
      setIsDrafting(false);
    }
    return null;
  }, [alertId]);

  return { isDrafting, message, draft };
}
