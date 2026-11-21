import type { ApprovalRequest, Delivery } from "../../api/types";

type ChannelTypeName = Delivery["channel_type"];

/** "settlements-engine" becomes "Settlements engine". */
export function humanizeId(id: string): string {
  const text = id.replaceAll(/[-_]+/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** Recipient and actor ids are first names in the config ("anna"); show them capitalised. */
export function personName(id: string, displayName?: string | null): string {
  if (displayName) return displayName.split(" ")[0] ?? displayName;
  return humanizeId(id.replace(/-operator$/, " (operator)"));
}

interface ActionWords {
  /** Used in "Waiting for Piotr to approve <noun>". */
  readonly noun: string;
  readonly running: string;
  readonly done: string;
  readonly failed: string;
  readonly skipped: string;
}

const ACTION_WORDS: Readonly<Record<string, ActionWords>> = {
  "http-health-check": {
    noun: "the health check",
    running: "Running health check",
    done: "Health check passed",
    failed: "Health check failed",
    skipped: "Health check skipped",
  },
  "retry-workflow": {
    noun: "the workflow retry",
    running: "Retrying the workflow",
    done: "Workflow retried",
    failed: "Retry failed",
    skipped: "Retry skipped",
  },
  escalate: {
    noun: "escalation",
    running: "Escalating",
    done: "Escalated",
    failed: "Escalation failed",
    skipped: "Escalation skipped",
  },
  "open-ticket": {
    noun: "opening a ticket",
    running: "Opening a ticket",
    done: "Ticket opened",
    failed: "Opening the ticket failed",
    skipped: "Ticket skipped",
  },
  "restart-pricing-adapter": {
    noun: "the adapter restart",
    running: "Restarting the pricing adapter",
    done: "Pricing adapter restarted",
    failed: "Adapter restart failed",
    skipped: "Adapter restart skipped",
  },
};

export function actionWords(actionId: string): ActionWords {
  const fallback = humanizeId(actionId).toLowerCase();
  return (
    ACTION_WORDS[actionId] ?? {
      noun: fallback,
      running: `Running ${fallback}`,
      done: `${humanizeId(actionId)} done`,
      failed: `${humanizeId(actionId)} failed`,
      skipped: `${humanizeId(actionId)} skipped`,
    }
  );
}

const SENT_VERB: Record<ChannelTypeName, string> = {
  ui: "Posted to the inbox",
  email: "Emailed",
  sms: "Texted",
  phone: "Called",
  webhook: "Sent a webhook to",
};

const CHANNEL_NOUN: Record<ChannelTypeName, string> = {
  ui: "the inbox",
  email: "email",
  sms: "SMS",
  phone: "phone",
  webhook: "webhook",
};

const APPROVAL_VIA: Record<NonNullable<ApprovalRequest["decided_via"]>, string> = {
  ui: "in the inbox",
  sms: "by SMS",
  phone: "by phone",
};

export function approvalViaWords(via: ApprovalRequest["decided_via"]): string {
  return via ? APPROVAL_VIA[via] : "";
}

/** "Emailed Anna", "Called Piotr", "Asked Anna to approve by SMS". */
export function deliveryWords(delivery: Delivery): { title: string; state: DeliveryState } {
  const channel = delivery.channel_type;
  const who = delivery.recipient_id ? personName(delivery.recipient_id) : null;
  const fallbackNote = delivery.is_fallback ? " (fallback)" : "";
  const target = who ?? (channel === "webhook" ? humanizeId(delivery.channel_id) : "");
  const sent =
    delivery.purpose === "approval_request"
      ? `Asked ${who ?? "the team"} to approve by ${CHANNEL_NOUN[channel]}`
      : channel === "ui"
        ? SENT_VERB.ui
        : `${SENT_VERB[channel]} ${target || "the team"}`.trim();
  const group = delivery.purpose === "group_summary" ? " (group summary)" : "";

  switch (delivery.status) {
    case "delivered":
    case "sent":
      return { title: `${sent}${group}${fallbackNote}`, state: "done" };
    case "pending":
      return {
        title: `Sending ${CHANNEL_NOUN[channel]}${who ? ` to ${who}` : ""}${group}`,
        state: "running",
      };
    case "failed":
      return {
        title: `${capitalize(CHANNEL_NOUN[channel])}${who ? ` to ${who}` : ""} failed, retrying (attempt ${String(delivery.attempt)})`,
        state: "failed",
      };
    case "dead_lettered":
      return {
        title: `Could not reach ${who ?? "the team"} by ${CHANNEL_NOUN[channel]}, kept for retry`,
        state: "failed",
      };
    case "suppressed":
      return {
        title: `Skipped ${CHANNEL_NOUN[channel]}${who ? ` to ${who}` : ""}`,
        state: "skipped",
      };
  }
}

type DeliveryState = "done" | "running" | "failed" | "skipped";

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}
