import type {
  ConditionLeaf,
  ConfigValidationError,
  FieldMappingSpec,
  NormalizedFieldMappings,
  SchemaProfile,
} from "../../api/types";

export type SampleEvent = Record<string, unknown>;
export type FieldName = keyof NormalizedFieldMappings;
export type Match = SchemaProfile["match"];

export const FIELD_NAMES: readonly FieldName[] = [
  "type",
  "source",
  "severity",
  "occurred_at",
  "entity",
];
export const SEVERITIES = ["debug", "info", "warning", "error", "critical"] as const;
export const TIME_FORMATS = ["iso8601", "epoch_ms", "epoch_s"] as const;
const SLUG = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export function isValidProfileId(id: string): boolean {
  return SLUG.test(id);
}

/** Flattens nested objects to dotted key paths; arrays and empty objects are leaves. */
export function flattenKeyPaths(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return [];
  const paths: string[] = [];
  for (const [key, child] of Object.entries(value)) {
    const path = prefix === "" ? key : `${prefix}.${key}`;
    const nested = flattenKeyPaths(child, path);
    if (nested.length > 0) paths.push(...nested);
    else paths.push(path);
  }
  return paths.sort();
}

/** Parses pasted text into a JSON object, or returns an error message. */
export function parseSampleJson(text: string): { sample: SampleEvent } | { error: string } {
  try {
    const parsed: unknown = JSON.parse(text);
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
      return { error: "The sample must be a JSON object." };
    }
    return { sample: parsed as SampleEvent };
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Invalid JSON" };
  }
}

export function emptySpec(): FieldMappingSpec {
  return { path: null, const: null, format: null, value_map: {}, default: null };
}

/** A string mapping is shorthand for a path. */
export function toSpec(value: NormalizedFieldMappings[FieldName]): FieldMappingSpec | null {
  if (value === null) return null;
  return typeof value === "string" ? { ...emptySpec(), path: value } : value;
}

/** Collapses a plain path spec back to the string shorthand; empty specs become null. */
export function fromSpec(spec: FieldMappingSpec | null): NormalizedFieldMappings[FieldName] {
  if (spec === null || (spec.path === null && spec.const === null)) return null;
  const isPlain =
    spec.const === null &&
    spec.format === null &&
    spec.default === null &&
    Object.keys(spec.value_map ?? {}).length === 0;
  return isPlain ? spec.path : spec;
}

/** The match as a list of `exists` leaves, or null when it has another shape (kept as is). */
export function existsPaths(match: Match): string[] | null {
  const leaves: unknown[] = "all" in match ? match.all : [match];
  const paths: string[] = [];
  for (const leaf of leaves) {
    if (typeof leaf !== "object" || leaf === null || !("field" in leaf) || !("op" in leaf)) {
      return null;
    }
    const { field, op } = leaf as ConditionLeaf;
    if (op !== "exists") return null;
    paths.push(field);
  }
  return paths;
}

export function matchFromPaths(paths: readonly string[]): Match {
  const leaves = paths.map((field): ConditionLeaf => ({ field, op: "exists", value: true }));
  return leaves.length === 1 && leaves[0] ? leaves[0] : { all: leaves };
}

/** Details whose path (without the request prefix) is `prefix` or below it. */
export function errorsUnder(
  errors: readonly ConfigValidationError[],
  prefix: string,
): ConfigValidationError[] {
  return errors.filter((e) => {
    const path = e.path.replace(/^(body\.)?schema_profile\.?/, "");
    return path === prefix || path.startsWith(`${prefix}.`);
  });
}

export function unmatchedErrors(errors: readonly ConfigValidationError[]): ConfigValidationError[] {
  const prefixes = ["id", "description", "priority", "match", "fingerprint", "fields"];
  return errors.filter((e) => !prefixes.some((p) => errorsUnder([e], p).length > 0));
}
