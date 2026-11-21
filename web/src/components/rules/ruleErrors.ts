import type { ConfigValidationError } from "../../api/types";

/** Maps a dot path (e.g. "when.all.0.field") to a 1-based YAML line by a simple key search. */
export function lineForPath(yaml: string, path: string): number | null {
  const lines = yaml.split("\n");
  const keys = path.split(".").filter((part) => part !== "" && !/^\d+$/.test(part));
  for (let i = keys.length - 1; i >= 0; i -= 1) {
    const key = keys[i];
    if (key === undefined) continue;
    const pattern = new RegExp(
      `^\\s*(-\\s+)*["']?${key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}["']?\\s*:`,
    );
    const index = lines.findIndex((line) => pattern.test(line));
    if (index >= 0) return index + 1;
  }
  return null;
}

export function errorLines(yaml: string, errors: readonly ConfigValidationError[]): number[] {
  const found = errors.map((error) => lineForPath(yaml, error.path));
  return found.filter((line): line is number => line !== null);
}

/** `when.all[0].value` (rule validation) and `when.all.0.value` (Pydantic) name the same spot. */
export function normalizePath(path: string): string {
  return path.replace(/\[(\d+)\]/g, ".$1");
}

const withNormalPath = (error: ConfigValidationError): ConfigValidationError => ({
  ...error,
  path: normalizePath(error.path),
});

/** Reads ErrorResponse.details from a failed response body, if present. */
export function detailsFromBody(body: unknown): ConfigValidationError[] {
  if (typeof body !== "object" || body === null || !("details" in body)) return [];
  const details = (body as { details?: unknown }).details;
  if (!Array.isArray(details)) return [];
  return details
    .filter(
      (item): item is ConfigValidationError =>
        typeof item === "object" &&
        item !== null &&
        typeof (item as { path?: unknown }).path === "string" &&
        typeof (item as { message?: unknown }).message === "string",
    )
    .map(withNormalPath);
}

export function messageFromBody(body: unknown, fallback: string): string {
  if (typeof body === "object" && body !== null && "message" in body) {
    const message = (body as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}

const FIELD_WORDS: Record<string, string> = {
  id: "Rule id",
  team: "Team",
  description: "Description",
  enabled: "Enabled",
  when: "Condition",
  severity: "Severity",
  route: "Who and how",
  "route.teams": "Teams",
  "route.recipients": "People",
  "route.channels": "Channels",
  present: "Alert text",
  "present.title": "Alert title",
  "present.body": "Alert body",
  dedup: "Duplicates",
  "dedup.window": "Duplicate window",
  group: "Grouping",
  throttle: "Limit per person",
  runbook: "Runbook",
};

/** Names where a validation error belongs, in words: "when.all.1.value" becomes "Condition 2, value". */
export function humanPath(path: string): string {
  const leaf = /(?:^|\.)all\.(\d+)\.(field|op|value)$/.exec(path);
  if (leaf?.[1] && leaf[2]) {
    return `Condition ${String(Number(leaf[1]) + 1)}, ${leaf[2] === "op" ? "operator" : leaf[2]}`;
  }
  const single = /^when\.(field|op|value)$/.exec(path);
  if (single?.[1]) return `Condition 1, ${single[1] === "op" ? "operator" : single[1]}`;
  if (path === "") return "The rule";
  const exact = FIELD_WORDS[path] ?? FIELD_WORDS[path.split(".").slice(0, 2).join(".")];
  return exact ?? FIELD_WORDS[path.split(".")[0] ?? ""] ?? path;
}

/** Messages for the three inputs of condition row `index`. */
export function conditionErrors(
  errors: readonly ConfigValidationError[],
  index: number,
  isSingleLeaf: boolean,
): { field?: string; op?: string; value?: string } {
  const result: { field?: string; op?: string; value?: string } = {};
  for (const error of errors) {
    const match = isSingleLeaf
      ? /^when\.(field|op|value)$/.exec(error.path)
      : new RegExp(`(?:^|\\.)all\\.${String(index)}\\.(field|op|value)$`).exec(error.path);
    const key = match?.[1] as "field" | "op" | "value" | undefined;
    if (key && result[key] === undefined) result[key] = friendlyMessage(error.path, error.message);
  }
  return result;
}

/** True when the error is shown at a condition input, so the list below skips it. */
export function isConditionFieldError(error: ConfigValidationError): boolean {
  return /(?:^|\.)(all\.\d+\.|when\.)(field|op|value)$/.test(error.path);
}

/** Rewrites the raw pydantic wording of common problems into advice; other messages pass through. */
export function friendlyMessage(path: string, message: string): string {
  if (path === "id" && /pattern|match/i.test(message)) {
    return "Use lowercase letters, digits and dashes, starting with a letter or digit.";
  }
  if (/invalid YAML/i.test(message)) {
    // The parser's own words are for engineers; point at the line instead.
    const lines = [...message.matchAll(/line (\d+), column (\d+)/g)];
    const last = lines.at(-1);
    return last
      ? `The text cannot be read yet. Check line ${last[1] ?? ""} near column ${last[2] ?? ""}.`
      : "The text cannot be read yet. Check the indentation and colons.";
  }
  if (/field required|missing/i.test(message)) return "This is required.";
  if (/at least 1 character/i.test(message)) return "This cannot be empty.";
  return message;
}

const isUnionNoise = (e: ConfigValidationError) =>
  e.path.startsWith("when") && /^(Extra inputs are not permitted|Field required)$/.test(e.message);

/**
 * The condition is a union of shapes, so the API reports every shape that did not fit. Keep the
 * real problem, or one plain sentence when nothing more specific is known; drop repeats.
 */
export function tidyErrors(raw: readonly ConfigValidationError[]): ConfigValidationError[] {
  const errors = raw.map(withNormalPath);
  const hasReal = errors.some((e) => e.path.startsWith("when") && !isUnionNoise(e));
  const kept = errors.filter((e) => !isUnionNoise(e));
  const summary: ConfigValidationError[] =
    !hasReal && kept.length < errors.length
      ? [
          {
            path: "when",
            message: "The condition is not valid. Check its fields in Advanced (YAML).",
          },
        ]
      : [];
  const seen = new Set<string>();
  return [...summary, ...kept].filter((e) => {
    const key = `${e.path}|${e.message}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
