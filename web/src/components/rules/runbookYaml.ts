const RUNBOOK_LINE = /^runbook:[ \t]*(.*)$/m;

/** The rule's top-level `runbook:` id, or "" when the rule has none. */
export function readRunbookFromRuleYaml(yaml: string): string {
  const match = RUNBOOK_LINE.exec(yaml);
  const value = (match?.[1] ?? "").replace(/\s+#.*$/, "").trim();
  return value.replace(/^["']|["']$/g, "");
}

/**
 * Sets, replaces or removes the top-level `runbook:` line. Only that one line changes, so the
 * rest of the YAML (comments, order, formatting) stays exactly as the person wrote it.
 */
export function writeRunbookToRuleYaml(yaml: string, runbookId: string): string {
  if (RUNBOOK_LINE.test(yaml)) {
    return runbookId === ""
      ? yaml.replace(/^runbook:.*(\r?\n)?/m, "")
      : yaml.replace(RUNBOOK_LINE, `runbook: ${runbookId}`);
  }
  if (runbookId === "") return yaml;
  const body = yaml.replace(/\s*$/, "");
  return `${body}\nrunbook: ${runbookId}\n`;
}
