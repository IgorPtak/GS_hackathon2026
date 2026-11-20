import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { ApprovalRequest } from "../../api/types";

export type DecisionKind = "approve" | "reject";

/** Sends one decision (via "ui"); `errors` is keyed by approval request id. */
export function useApprovalDecision(team: string, onDecided: (request: ApprovalRequest) => void) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});

  const decide = useCallback(
    async (id: string, decision: DecisionKind, comment: string) => {
      setBusyId(id);
      setErrors((prev) => ({ ...prev, [id]: "" }));
      let message = "";
      try {
        const { data, error, response } = await apiClient.POST(
          "/api/v1/approvals/{approval_request_id}/decision",
          {
            params: { path: { approval_request_id: id } },
            body: {
              decision,
              actor: { id: `${team}-operator`, display_name: null },
              via: "ui",
              comment: comment.trim() === "" ? null : comment.trim(),
            },
          },
        );
        if (data) onDecided(data);
        else if (response.status === 409)
          message = error.message.startsWith("Already")
            ? error.message
            : `Already decided: ${error.message}`;
        else message = `Could not send the decision (API error ${String(response.status)}).`;
      } catch (e) {
        message = `Could not send the decision: ${e instanceof Error ? e.message : "API unreachable"}.`;
      } finally {
        setBusyId(null);
      }
      setErrors((prev) => ({ ...prev, [id]: message }));
    },
    [team, onDecided],
  );

  return { busyId, errors, decide };
}
