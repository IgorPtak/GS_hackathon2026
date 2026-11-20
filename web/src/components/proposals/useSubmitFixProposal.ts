import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { ConfigValidationError, FixProposal, FixProposalCreate } from "../../api/types";
import { detailsFromBody, messageFromBody } from "../rules/ruleErrors";

type CreateBody = Omit<FixProposalCreate, "proposed_by">;

/** POST /alerts/{id}/fix-proposals; 422 details are kept by path. */
export function useSubmitFixProposal(alertId: string, team: string) {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [details, setDetails] = useState<readonly ConfigValidationError[]>([]);

  const submit = useCallback(
    async (body: CreateBody): Promise<FixProposal | null> => {
      setIsSubmitting(true);
      setMessage(null);
      setDetails([]);
      try {
        const { data, error, response } = await apiClient.POST(
          "/api/v1/alerts/{alert_id}/fix-proposals",
          {
            params: { path: { alert_id: alertId } },
            body: { ...body, proposed_by: { id: `${team}-operator`, display_name: null } },
          },
        );
        if (data) return data;
        setDetails(detailsFromBody(error));
        setMessage(
          messageFromBody(
            error,
            `Could not send the proposal (API error ${String(response.status)})`,
          ),
        );
      } catch (e) {
        setMessage(e instanceof Error ? e.message : "API unreachable");
      } finally {
        setIsSubmitting(false);
      }
      return null;
    },
    [alertId, team],
  );

  return { isSubmitting, message, details, submit };
}
