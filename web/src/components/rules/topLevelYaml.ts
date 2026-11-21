/** Read and write single-line top-level scalars (`id`, `description`) of a rule's YAML text. */

export type TopLevelKey = "id" | "description";

function lineOf(key: TopLevelKey): RegExp {
  return new RegExp(`^${key}:[ \\t]*(.*)$`, "m");
}

/** The scalar after `key:`; quoted JSON-style strings are unquoted. */
export function readTopLevel(yaml: string, key: TopLevelKey): string {
  const raw = (lineOf(key).exec(yaml)?.[1] ?? "").trim();
  if (raw.startsWith('"')) {
    try {
      const parsed: unknown = JSON.parse(raw);
      return typeof parsed === "string" ? parsed : raw;
    } catch {
      return raw;
    }
  }
  return raw.replace(/^'(.*)'$/, "$1");
}

/** Rewrites (or adds) `key:`; the value is always double-quoted so any text stays valid YAML. */
export function writeTopLevel(yaml: string, key: TopLevelKey, value: string): string {
  const line = `${key}: ${JSON.stringify(value)}`;
  if (lineOf(key).test(yaml)) return yaml.replace(lineOf(key), () => line);
  return `${line}\n${yaml}`;
}

/** Starting point for "New rule": one condition to edit, the default route, a plain alert. */
export function newRuleYaml(team: string): string {
  return [
    'id: ""',
    `team: ${team}`,
    'description: ""',
    'when: { field: payload.field, op: eq, value: "" }',
    "route:",
    "  channels: [ui, email]",
    "present:",
    '  title: "New alert"',
    '  body: ""',
    "",
  ].join("\n");
}
