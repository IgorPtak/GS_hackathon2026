import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { FixProposal } from "../../api/types";

/** Accept / reject one proposal; `errors` is keyed by proposal id. */
export function useFixDecision(team: string, onDecided: (proposal: FixProposal) => void) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});

  const decide = useCallback(
    async (id: string, decision: "accept" | "reject", comment: string) => {
      setBusyId(id);
      setErrors((prev) => ({ ...prev, [id]: "" }));
      let message = "";
      try {
        const { data, response } = await apiClient.POST(
          "/api/v1/fix-proposals/{proposal_id}/decision",
          {
            params: { path: { proposal_id: id } },
            body: {
              decision,
              actor: { id: `${team}-operator`, display_name: null },
              comment: comment.trim() === "" ? null : comment.trim(),
            },
          },
        );
        if (data) onDecided(data);
        else if (response.status === 409) message = "Already decided";
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
