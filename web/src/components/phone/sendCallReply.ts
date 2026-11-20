import { apiClient } from "../../api/client";

export interface CallReplyOutcome {
  message: string;
  isOk: boolean;
}

/** Posts a reply typed on the call keypad and maps the outcome to a message. */
export async function sendCallReply(recipientId: string, text: string): Promise<CallReplyOutcome> {
  try {
    const { data, response } = await apiClient.POST("/api/v1/phone-simulator/replies", {
      body: { recipient_id: recipientId, text },
    });
    if (data) return { message: data.message, isOk: data.is_understood };
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
