import type { ConditionLeaf } from "../../api/types";
import {
  UnsupportedYamlError,
  formatScalar,
  parseFlowMapping,
  parseScalar,
  splitKeyValue,
} from "./yamlScalars";

/** Pure helpers: read and rewrite only the `when:` block of a rule's YAML text. */

export type ConditionOp = ConditionLeaf["op"];

export const CONDITION_OPS: readonly ConditionOp[] = [
  "eq",
  "ne",
  "gt",
  "gte",
  "lt",
  "lte",
  "in",
  "glob",
  "regex",
  "exists",
  "severity_gte",
  "time_between",
];

export type ParsedWhen =
  | { readonly kind: "form"; readonly leaves: ConditionLeaf[]; readonly isSingleLeaf: boolean }
  | { readonly kind: "complex" };

interface WhenBlock {
  readonly start: number;
  readonly end: number; // exclusive; trailing blank lines are not part of the block
}

function findWhenBlock(lines: readonly string[]): WhenBlock | null {
  const start = lines.findIndex((line) => /^when:(\s|$)/.test(line));
  if (start < 0) return null;
  let last = start + 1;
  for (let i = start + 1; i < lines.length; i += 1) {
    const line = lines[i] ?? "";
    if (line.trim() !== "" && !/^\s/.test(line)) break;
    if (line.trim() !== "") last = i + 1;
  }
  return { start, end: last };
}

function toLeaf(pairs: readonly (readonly [string, string])[]): ConditionLeaf {
  const raw = new Map(pairs);
  if (raw.size !== pairs.length) throw new UnsupportedYamlError("duplicate key");
  const field = parseScalar(raw.get("field") ?? "");
  const op = raw.get("op")?.trim();
  const isKnownOp = CONDITION_OPS.some((known) => known === op);
  const hasOnlyLeafKeys = [...raw.keys()].every((key) => ["field", "op", "value"].includes(key));
  // An empty field is still a leaf: the form shows it and the API asks for it to be filled in.
  if (typeof field !== "string" || !isKnownOp || !hasOnlyLeafKeys) {
    throw new UnsupportedYamlError("not a leaf");
  }
  return { field, op: op as ConditionOp, value: parseScalar(raw.get("value") ?? "") };
}

function blockPairs(lines: readonly string[]): [string, string][] {
  return lines.map((line) => splitKeyValue(line.trim()));
}

/** Groups `all:` items: a `- ` line starts an item, deeper lines continue its block mapping. */
function parseAllItems(lines: readonly string[]): ConditionLeaf[] {
  const itemIndent = (lines[0] ?? "").length - (lines[0] ?? "").trimStart().length;
  const items: string[][] = [];
  for (const line of lines) {
    const indent = line.length - line.trimStart().length;
    if (indent === itemIndent && line.trimStart().startsWith("- ")) {
      items.push([line.trimStart().slice(2).trim()]);
    } else if (indent === itemIndent + 2 && items.length > 0) {
      items[items.length - 1]?.push(line.trim());
    } else {
      throw new UnsupportedYamlError("list layout");
    }
  }
  return items.map((item) => {
    const first = item[0] ?? "";
    if (first.startsWith("{")) {
      if (item.length > 1) throw new UnsupportedYamlError("mixed item");
      return toLeaf(parseFlowMapping(first));
    }
    return toLeaf(blockPairs(item));
  });
}

function parseBlock(headRest: string, body: readonly string[]): ParsedWhen {
  const lines = body.filter((line) => line.trim() !== "");
  if (lines.some((line) => line.trim().startsWith("#"))) throw new UnsupportedYamlError("comment");
  if (headRest !== "") {
    if (lines.length > 0) throw new UnsupportedYamlError("mixed");
    return { kind: "form", leaves: [toLeaf(parseFlowMapping(headRest))], isSingleLeaf: true };
  }
  const baseIndent = (lines[0] ?? "").length - (lines[0] ?? "").trimStart().length;
  if ((lines[0] ?? "").trim() === "all:") {
    const leaves = parseAllItems(lines.slice(1));
    if (leaves.length === 0) throw new UnsupportedYamlError("empty all");
    return { kind: "form", leaves, isSingleLeaf: false };
  }
  if (lines.some((line) => line.length - line.trimStart().length !== baseIndent)) {
    throw new UnsupportedYamlError("indent");
  }
  return { kind: "form", leaves: [toLeaf(blockPairs(lines))], isSingleLeaf: true };
}

/** Reads the `when:` block if it is one leaf or a flat `all` of leaves; otherwise `complex`. */
export function parseWhenFromRuleYaml(yaml: string): ParsedWhen {
  const lines = yaml.split("\n");
  const block = findWhenBlock(lines);
  if (!block) return { kind: "complex" };
  try {
    const head = (lines[block.start] ?? "").replace(/^when:/, "").trim();
    return parseBlock(head, lines.slice(block.start + 1, block.end));
  } catch (error) {
    if (error instanceof UnsupportedYamlError) return { kind: "complex" };
    throw error;
  }
}

function formatLeaf(leaf: ConditionLeaf): string {
  const field = formatScalar(leaf.field);
  return `{ field: ${field}, op: ${leaf.op}, value: ${formatScalar(leaf.value)} }`;
}

/** Serializes leaves as a `when:` block (single leaf inline, otherwise a flat `all`). */
export function formatWhen(leaves: readonly ConditionLeaf[], isSingleLeaf: boolean): string[] {
  const [only] = leaves;
  if (isSingleLeaf && leaves.length === 1 && only) return [`when: ${formatLeaf(only)}`];
  return ["when:", "  all:", ...leaves.map((leaf) => `    - ${formatLeaf(leaf)}`)];
}

/** Replaces only the `when:` block lines; every other line stays byte-identical. */
export function replaceWhenInRuleYaml(
  yaml: string,
  leaves: readonly ConditionLeaf[],
  isSingleLeaf: boolean,
): string {
  const lines = yaml.split("\n");
  const block = findWhenBlock(lines);
  if (!block) return yaml;
  lines.splice(block.start, block.end - block.start, ...formatWhen(leaves, isSingleLeaf));
  return lines.join("\n");
}
