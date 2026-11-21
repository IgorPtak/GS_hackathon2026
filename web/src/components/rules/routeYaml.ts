/** Read and rewrite only the `route:` block of a rule's YAML text (flow lists only). */

export interface RouteDraft {
  readonly teams: readonly string[];
  readonly recipients: readonly string[];
  readonly channels: readonly string[];
}

export const DEFAULT_CHANNELS: readonly string[] = ["ui", "email"];
const KEYS = ["teams", "recipients", "channels"] as const;

function findRouteBlock(lines: readonly string[]): { start: number; end: number } | null {
  const start = lines.findIndex((line) => /^route:(\s|$)/.test(line));
  if (start < 0) return null;
  let end = start + 1;
  for (let i = start + 1; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    if (line.trim() !== "" && !/^\s/.test(line)) break;
    if (line.trim() !== "") end = i + 1;
  }
  return { start, end };
}

function parseFlowList(text: string): string[] | null {
  const match = /^\[(.*)\]$/.exec(text.trim());
  if (!match) return null;
  const items = (match[1] ?? "")
    .split(",")
    .map((item) => item.trim().replace(/^["']|["']$/g, ""))
    .filter((item) => item !== "");
  return items.every((item) => /^[A-Za-z0-9_.-]+$/.test(item)) ? items : null;
}

/** Route as the form can edit it, or null when the block has a shape only YAML should touch. */
export function parseRouteFromRuleYaml(yaml: string): RouteDraft | null {
  const lines = yaml.split("\n");
  const block = findRouteBlock(lines);
  if (!block) return { teams: [], recipients: [], channels: DEFAULT_CHANNELS };
  if ((lines[block.start] ?? "").replace(/^route:/, "").trim() !== "") return null;
  const found: Record<string, string[]> = {};
  const body = lines.slice(block.start + 1, block.end).filter((line) => line.trim() !== "");
  for (let i = 0; i < body.length; i += 1) {
    const match = /^\s+(teams|recipients|channels):\s*(.*)$/.exec(body[i] ?? "");
    if (!match?.[1] || match[1] in found) return null;
    let list: string[] | null;
    if ((match[2] ?? "").trim() === "") {
      // Block style, as the API serializes it: "- item" lines under the key.
      list = [];
      while (/^\s*-\s+\S+\s*$/.test(body[i + 1] ?? "")) {
        i += 1;
        list.push(
          (body[i] ?? "")
            .replace(/^\s*-\s+/, "")
            .trim()
            .replace(/^["']|["']$/g, ""),
        );
      }
      if (!list.every((item) => /^[A-Za-z0-9_.-]+$/.test(item))) list = null;
    } else {
      list = parseFlowList(match[2] ?? "");
    }
    if (!list) return null;
    found[match[1]] = list;
  }
  return {
    teams: found.teams ?? [],
    recipients: found.recipients ?? [],
    channels: found.channels ?? DEFAULT_CHANNELS,
  };
}

function formatRoute(route: RouteDraft): string[] {
  const lines = ["route:"];
  for (const key of KEYS) {
    if (key !== "channels" && route[key].length === 0) continue;
    lines.push(`  ${key}: [${route[key].join(", ")}]`);
  }
  return lines;
}

/** Replaces the `route:` block (or inserts it before `present:`); other lines stay untouched. */
export function replaceRouteInRuleYaml(yaml: string, route: RouteDraft): string {
  const lines = yaml.split("\n");
  const block = findRouteBlock(lines);
  if (block) {
    lines.splice(block.start, block.end - block.start, ...formatRoute(route));
    return lines.join("\n");
  }
  const present = lines.findIndex((line) => /^present:/.test(line));
  const at = present >= 0 ? present : lines.length;
  lines.splice(at, 0, ...formatRoute(route));
  return lines.join("\n");
}
