import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { FixProposal } from "../../api/types";

export type FixDecisionKind = "accept" | "reject";

interface BusyDecision {
  readonly id: string;
  readonly kind: FixDecisionKind;
}

/** Accept or reject one fix proposal; returns true when accepted by the server. */
export function useFixDecision(team: string, onDecided: (proposal: FixProposal) => void) {
  const [busy, setBusy] = useState<BusyDecision | null>(null);
  const [errors, setErrors] = useState<Readonly<Record<string, string>>>({});

  const decide = useCallback(
    async (id: string, decision: FixDecisionKind, comment: string): Promise<boolean> => {
      setBusy({ id, kind: decision });
      setErrors((prev) => ({ ...prev, [id]: "" }));
      let message = "";
      let succeeded = false;
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
        if (data) {
          onDecided(data);
          succeeded = true;
        } else if (response.status === 409) {
          message = "This proposal was already decided.";
        } else {
          message = `Could not send the decision (API error ${String(response.status)}).`;
        }
      } catch (e) {
        message = `Could not send the decision: ${e instanceof Error ? e.message : "API unreachable"}.`;
      } finally {
        setBusy(null);
      }
      if (message) setErrors((prev) => ({ ...prev, [id]: message }));
      return succeeded;
    },
    [team, onDecided],
  );

  return {
    busyId: busy?.id ?? null,
    busyKind: busy?.kind ?? null,
    errors,
    decide,
  };
}
