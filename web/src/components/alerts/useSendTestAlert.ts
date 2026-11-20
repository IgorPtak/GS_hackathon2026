import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import { useToast } from "../ui/toastContext";
import { buildTestAlert } from "./testAlertFixtures";

/** Posts a fresh test event through the ingest proxy and reports the outcome with a toast. */
export function useSendTestAlert(teamId: string, teamLabel: string) {
  const toast = useToast();
  const [isSending, setIsSending] = useState(false);

  const send = useCallback(async () => {
    const testAlert = buildTestAlert(teamId);
    setIsSending(true);
    try {
      const { response } = await apiClient.POST("/api/v1/ingest/{source_id}", {
        params: { path: { source_id: testAlert.sourceId } },
        body: testAlert.payload,
      });
      if (response.status === 202) {
        const isOtherTeam = testAlert.teamId !== teamId;
        toast.show(
          isOtherTeam
            ? `Test alert sent to ${testAlert.teamId} (not ${teamLabel})`
            : "Test alert sent",
        );
      } else {
        toast.show(
          `The test alert was not accepted (error ${String(response.status)}). Try again.`,
          "error",
        );
      }
    } catch {
      toast.show(
        "Could not reach the service. Check that the stack is running and try again.",
        "error",
      );
    } finally {
      setIsSending(false);
    }
  }, [teamId, teamLabel, toast]);

  return { isSending, send };
}
