import type { PhoneMessage } from "../../api/types";

export type DevPhoneState = "call" | "incall" | null;

/**
 * Dev-only query param overrides (`?phoneState=call|incall` and `?recipient=<id>`) so
 * headless screenshots can deterministically capture ringing and active-call states.
 */
export function readDevPhoneState(): DevPhoneState {
  if (!import.meta.env.DEV || typeof window === "undefined") return null;
  const raw = new URLSearchParams(window.location.search).get("phoneState");
  if (raw === "call" || raw === "incall") return raw;
  return null;
}

export function readUrlRecipientId(): string | null {
  if (typeof window === "undefined") return null;
  const raw = new URLSearchParams(window.location.search).get("recipient");
  return raw && raw.trim() !== "" ? raw.trim() : null;
}

/** Picks the latest real call message for dev override, or builds a realistic preview message. */
export function resolveDevCallMessage(
  messages: readonly PhoneMessage[],
  recipientId: string,
): PhoneMessage {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const item = messages[i];
    if (item && item.channel_type === "phone" && item.approval_code) return item;
  }
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const item = messages[i];
    if (item && item.approval_code) return item;
  }
  return {
    id: "dev-preview-call",
    recipient_id: recipientId,
    channel_type: "phone",
    to: "+48600000001",
    text: "Settlement workflow WF-123 failed twice.\nEscalate to the settlements lead?\nReply APPROVE 4602 or REJECT 4602",
    alert_id: "alt-preview",
    delivery_id: 0,
    approval_code: "4602",
    at: new Date().toISOString(),
  };
}
