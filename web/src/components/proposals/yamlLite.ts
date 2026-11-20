function scalar(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function isContainer(value: unknown): value is object {
  if (typeof value !== "object" || value === null) return false;
  return Array.isArray(value) ? value.length > 0 : Object.keys(value).length > 0;
}

function lines(value: unknown, indent: number): string[] {
  const pad = " ".repeat(indent);
  if (Array.isArray(value)) {
    return value.flatMap((item: unknown) => {
      if (!isContainer(item)) return [`${pad}- ${scalar(item)}`];
      const [first = "", ...rest] = lines(item, indent + 2);
      return [`${pad}- ${first.trimStart()}`, ...rest];
    });
  }
  if (typeof value === "object" && value !== null) {
    return Object.entries(value).flatMap(([key, item]) => {
      if (!isContainer(item)) {
        const empty = Array.isArray(item) ? "[]" : typeof item === "object" ? "{}" : null;
        return [`${pad}${key}: ${empty ?? scalar(item)}`];
      }
      return [`${pad}${key}:`, ...lines(item, indent + 2)];
    });
  }
  return [`${pad}${scalar(value)}`];
}

/** Small deterministic YAML-ish serializer (insertion order, JSON-quoted strings) for diffs only. */
export function toYamlLines(value: unknown): string[] {
  return lines(value, 0);
}
