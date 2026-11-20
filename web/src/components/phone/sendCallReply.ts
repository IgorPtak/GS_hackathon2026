import { apiClient } from "../../api/client";

export interface CallReplyOutcome {
  readonly message: string;
  readonly isOk: boolean;
}

function formatCallOutcome(
  command: "approve" | "reject",
  isUnderstood: boolean,
  backendMessage: string,
): CallReplyOutcome {
  if (isUnderstood) {
    return {
      message:
        command === "approve" ? "Approved. Escalating now." : "Rejected. Escalation cancelled.",
      isOk: true,
    };
  }
  if (command === "approve" && /no pending approval/i.test(backendMessage)) {
    return { message: "That code didn't match. Try again.", isOk: false };
  }
  return { message: backendMessage, isOk: false };
}

/** Posts a reply typed on the call keypad and maps the outcome to plain-language status copy. */
export async function sendCallReply(recipientId: string, text: string): Promise<CallReplyOutcome> {
  const command: "approve" | "reject" = text.toUpperCase().startsWith("REJECT")
    ? "reject"
    : "approve";
  try {
    const { data, response } = await apiClient.POST("/api/v1/phone-simulator/replies", {
      body: { recipient_id: recipientId, text },
    });
    if (data) return formatCallOutcome(command, data.is_understood, data.message);
    return {
      message:
        response.status === 404 || response.status === 503
          ? "Replies are not available yet."
          : `Could not send the reply (API error ${String(response.status)}).`,
      isOk: false,
    };
  } catch (e) {
    return {
      message: `Could not send the reply: ${e instanceof Error ? e.message : "API unreachable"}.`,
      isOk: false,
    };
  }
}
