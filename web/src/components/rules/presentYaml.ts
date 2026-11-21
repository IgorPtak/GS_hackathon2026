/** Read and rewrite `present.title` and `present.body` of a rule's YAML text, nothing else. */

export interface PresentDraft {
  readonly title: string;
  readonly body: string;
}

type PresentKey = keyof PresentDraft;

function findPresentBlock(lines: readonly string[]): { start: number; end: number } | null {
  const start = lines.findIndex((line) => /^present:(\s|$)/.test(line));
  if (start < 0) return null;
  let end = start + 1;
  for (let i = start + 1; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    if (line.trim() !== "" && !/^\s/.test(line)) break;
    if (line.trim() !== "") end = i + 1;
  }
  return { start, end };
}

function unquote(raw: string): string {
  const text = raw.trim();
  if (text.startsWith('"')) {
    try {
      const parsed: unknown = JSON.parse(text);
      return typeof parsed === "string" ? parsed : text;
    } catch {
      return text;
    }
  }
  return text.replace(/^'(.*)'$/, "$1").replace(/''/g, "'");
}

/**
 * Title and body as the form can edit them, or null when `present:` has a shape only the YAML
 * should touch (flow style, or a multi-line title or body).
 */
export function parsePresentFromRuleYaml(yaml: string): PresentDraft | null {
  const lines = yaml.split("\n");
  const block = findPresentBlock(lines);
  if (!block) return { title: "", body: "" };
  if ((lines[block.start] ?? "").replace(/^present:/, "").trim() !== "") return null;
  const draft: Record<PresentKey, string> = { title: "", body: "" };
  for (const line of lines.slice(block.start + 1, block.end)) {
    const match = /^ {2}(title|body):[ \t]*(.*)$/.exec(line);
    if (!match?.[1]) continue;
    const value = match[2] ?? "";
    if (/^[|>]/.test(value.trim())) return null;
    draft[match[1] as PresentKey] = unquote(value);
  }
  return draft;
}

/** Sets one key inside `present:` (adding the block if needed); other keys stay untouched. */
export function writePresentToRuleYaml(yaml: string, key: PresentKey, value: string): string {
  const lines = yaml.split("\n");
  const line = `  ${key}: ${JSON.stringify(value)}`;
  const block = findPresentBlock(lines);
  if (!block) {
    const body = yaml.replace(/\s*$/, "");
    return `${body}\npresent:\n${line}\n`;
  }
  const at = lines.findIndex(
    (candidate, index) =>
      index > block.start && index < block.end && candidate.startsWith(`  ${key}:`),
  );
  if (at >= 0) lines[at] = line;
  else lines.splice(key === "title" ? block.start + 1 : block.end, 0, line);
  return lines.join("\n");
}
