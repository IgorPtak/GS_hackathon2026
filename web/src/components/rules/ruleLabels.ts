import type { ConditionLeaf, Rule, Severity } from "../../api/types";

/** Plain-language operator labels; the keys are the exact contract ops written to the YAML. */
export const OP_LABELS: Record<ConditionLeaf["op"], string> = {
  eq: "is equal to",
  ne: "is not equal to",
  gt: "is greater than",
  gte: "is at least",
  lt: "is less than",
  lte: "is at most",
  in: "is one of",
  glob: "matches the pattern",
  regex: "matches the regex",
  exists: "must be",
};

export function opLabel(op: ConditionLeaf["op"]): string {
  return OP_LABELS[op];
}

const SEVERITY_WORDS: Record<Severity, string> = {
  critical: "Critical",
  error: "Error",
  warning: "Warning",
  info: "Info",
  debug: "Debug",
};

/** The rule's own severity, or a note that it follows the event. */
export function severityLabel(rule: Rule): string {
  return rule.severity ? SEVERITY_WORDS[rule.severity] : "From the event";
}

/** "Email and the app" style summary of the rule's default channels. */
export function channelsSummary(rule: Rule): string {
  const channels = rule.route?.channels ?? [];
  if (channels.length === 0) return "No channels";
  const words = channels.map((id) => (id === "ui" ? "the app" : id === "sms" ? "SMS" : id));
  const text = new Intl.ListFormat("en", { style: "long", type: "conjunction" }).format(words);
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "rates-large-rejections" reads as "Rates large rejections". */
export function ruleName(id: string): string {
  const spaced = id.replace(/[-_]+/g, " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}
