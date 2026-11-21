import type { Completion, CompletionContext, CompletionResult } from "@codemirror/autocomplete";

import { CONDITION_OPS } from "./conditionYaml";
import { OP_LABELS } from "./ruleLabels";

/** Keys of a rule and of its nested blocks, from contracts/schemas/config.Rule.schema.json. */
const KEYS_BY_PARENT: Record<string, readonly [string, string][]> = {
  "": [
    ["id", "Unique name, lowercase with dashes"],
    ["team", "Team that owns the rule"],
    ["description", "What the rule watches for"],
    ["enabled", "true or false"],
    ["when", "The condition that fires the rule"],
    ["severity", "Override the event's severity"],
    ["route", "Who is told, and how"],
    ["present", "Title, body and fields of the alert"],
    ["dedup", "Fold identical events into one alert"],
    ["group", "Summarise related alerts per window"],
    ["throttle", "Cap deliveries per person"],
    ["auto_resolve", "Close the alert by itself"],
    ["runbook", "Runbook id to attach"],
  ],
  route: [
    ["channels", "ui, email, sms, phone"],
    ["recipients", "People by id"],
    ["teams", "Whole teams by id"],
  ],
  present: [
    ["title", "Alert title, {{payload.x}} templates"],
    ["body", "Longer text"],
    ["fields", "Event fields to show"],
    ["color", "Accent colour"],
  ],
  dedup: [
    ["window", "For example 60s or 5m"],
    ["fingerprint", "Fields that make events identical"],
  ],
  group: [
    ["by", "Fields that group alerts"],
    ["window", "For example 5m"],
  ],
  throttle: [
    ["max_deliveries", "How many messages at most"],
    ["per", "Per time window, for example 1h"],
  ],
  auto_resolve: [
    ["on_resolution_event", "Close when a 'resolved' event arrives"],
    ["after_silence", "Close after quiet time, for example 30m"],
  ],
  when: [
    ["all", "Every condition must hold"],
    ["any", "At least one must hold"],
    ["not", "The condition must not hold"],
    ["field", "Dot path into the event"],
    ["op", "How to compare"],
    ["value", "What to compare with"],
  ],
};

const VALUES_BY_KEY: Record<string, readonly [string, string][]> = {
  op: CONDITION_OPS.map((op) => [op, OP_LABELS[op]] as [string, string]),
  severity: [
    ["debug", "Lowest"],
    ["info", "For information"],
    ["warning", "Worth a look"],
    ["error", "Something failed"],
    ["critical", "Wake someone up"],
  ],
  value: [
    ["warning", "With severity_gte: this level or above"],
    ["critical", "With severity_gte: only the top level"],
    ['"08:00-20:00"', "With time_between: UTC hours"],
    ['{ range: "08:00-20:00", timezone: Europe/Warsaw }', "With time_between: local hours"],
  ],
  enabled: [
    ["true", "The rule is active"],
    ["false", "The rule is paused"],
  ],
  on_resolution_event: [
    ["true", ""],
    ["false", ""],
  ],
  field: [
    ["normalized.severity", "Shared field from the schema profile"],
    ["normalized.type", "Shared field from the schema profile"],
    ["normalized.service", "Shared field from the schema profile"],
    ["normalized.message", "Shared field from the schema profile"],
    ["payload.", "A field of the raw event"],
  ],
};

const CHANNELS: readonly [string, string][] = [
  ["ui", "The Beacon inbox"],
  ["email", "Email"],
  ["sms", "Text message"],
  ["phone", "Phone call"],
];

function toOptions(entries: readonly [string, string][], type: string): Completion[] {
  return entries.map(([label, detail]) => ({ label, detail: detail || undefined, type }));
}

const CONDITION_KEYS = new Set(["all", "any", "not", "field", "op", "value"]);

/** The block the cursor line sits in: the nearest less-indented `key:` above it. */
function parentKey(context: CompletionContext, indent: number): string {
  const doc = context.state.doc;
  for (let number = doc.lineAt(context.pos).number - 1; number >= 1; number -= 1) {
    const text = doc.line(number).text;
    if (!text.trim()) continue;
    if (text.length - text.trimStart().length >= indent) continue;
    const key = /^\s*(?:-\s*)?([a-z_]+):/.exec(text)?.[1] ?? "";
    if (CONDITION_KEYS.has(key)) return "when";
    return key in KEYS_BY_PARENT ? key : "";
  }
  return "";
}

/**
 * Hints while typing rule YAML: keys valid at the cursor's level, then values for `op`,
 * `severity`, `field`, booleans and channel names. Explicit Ctrl+Space shows them too.
 */
export function completeRuleYaml(context: CompletionContext): CompletionResult | null {
  const line = context.state.doc.lineAt(context.pos);
  const before = line.text.slice(0, context.pos - line.from);

  const valueMatch = /^\s*(?:-\s*)?([a-z_]+):\s*([\w.-]*)$/.exec(before);
  if (valueMatch) {
    const [, key = "", typed = ""] = valueMatch;
    const values = key === "channels" ? CHANNELS : VALUES_BY_KEY[key];
    if (!values) return null;
    return {
      from: context.pos - typed.length,
      options: toOptions(values, "enum"),
      validFor: /^[\w.-]*$/,
    };
  }

  const listMatch = /[[,]\s*(\w*)$/.exec(before);
  if (listMatch && /channels:\s*\[/.test(before)) {
    const typed = listMatch[1] ?? "";
    return { from: context.pos - typed.length, options: toOptions(CHANNELS, "enum") };
  }

  const keyMatch = /^(\s*)(?:-\s*)?([a-z_]*)$/.exec(before);
  if (keyMatch && (keyMatch[2] !== "" || context.explicit)) {
    const indent = (keyMatch[1] ?? "").length;
    const parent = indent === 0 ? "" : parentKey(context, indent);
    const keys = KEYS_BY_PARENT[parent];
    if (!keys) return null;
    return {
      from: context.pos - (keyMatch[2] ?? "").length,
      options: keys.map(([label, detail]) => ({
        label,
        detail,
        type: "property",
        apply: `${label}: `,
      })),
      validFor: /^[a-z_]*$/,
    };
  }
  return null;
}
