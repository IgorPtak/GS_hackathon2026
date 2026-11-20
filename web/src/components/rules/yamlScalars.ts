/** Tiny parser/serializer for the YAML flow subset used by `when:` leaves. Throws on anything else. */

export class UnsupportedYamlError extends Error {}

const NUMBER = /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/;
const PLAIN_SAFE = /^[A-Za-z_][A-Za-z0-9_.\-*]*$/;
const RESERVED = new Set(["true", "false", "null", "yes", "no", "on", "off", "y", "n"]);
const OPENERS = new Map([
  ["[", "]"],
  ["{", "}"],
]);

/** Splits on top-level commas, ignoring commas inside quotes or brackets; rejects inline comments. */
export function splitTopLevel(text: string): string[] {
  const parts: string[] = [];
  const closers: string[] = [];
  let quote = "";
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text.charAt(i);
    if (quote) {
      if (ch === "\\" && quote === '"') i += 1;
      else if (ch === quote) quote = "";
    } else if (ch === '"' || ch === "'") {
      quote = ch;
    } else if (ch === "#" && (i === 0 || text.charAt(i - 1) === " ")) {
      throw new UnsupportedYamlError("comment");
    } else if (OPENERS.has(ch)) {
      closers.push(OPENERS.get(ch) ?? "");
    } else if (ch === closers[closers.length - 1]) {
      closers.pop();
    } else if (ch === "," && closers.length === 0) {
      parts.push(text.slice(start, i));
      start = i + 1;
    }
  }
  if (quote || closers.length > 0) throw new UnsupportedYamlError("unbalanced");
  parts.push(text.slice(start));
  return parts;
}

/** Parses one YAML scalar or flow list of scalars. */
export function parseScalar(raw: string): unknown {
  const text = raw.trim();
  if (text === "" || text === "null" || text === "~") return null;
  if (text === "true") return true;
  if (text === "false") return false;
  if (NUMBER.test(text)) return Number(text);
  if (text.startsWith('"')) return parseDoubleQuoted(text);
  if (text.startsWith("'") && text.endsWith("'") && text.length >= 2) {
    return text.slice(1, -1).replaceAll("''", "'");
  }
  if (text.startsWith("[") && text.endsWith("]")) {
    const inner = text.slice(1, -1).trim();
    return inner === "" ? [] : splitTopLevel(inner).map(parseScalar);
  }
  if (/^[{[\]}&*!|>%@`'"#]/.test(text) || /: |:$| #/.test(text)) {
    throw new UnsupportedYamlError("plain scalar");
  }
  if (RESERVED.has(text.toLowerCase())) throw new UnsupportedYamlError("ambiguous scalar");
  return text;
}

function parseDoubleQuoted(text: string): string {
  try {
    const value: unknown = JSON.parse(text);
    if (typeof value === "string") return value;
  } catch {
    // Falls through to the unsupported error below.
  }
  throw new UnsupportedYamlError("quoted scalar");
}

/** Parses `{ a: 1, b: x }` into key/value pairs (values stay raw text). */
export function parseFlowMapping(raw: string): [string, string][] {
  const text = raw.trim();
  if (!text.startsWith("{") || !text.endsWith("}")) throw new UnsupportedYamlError("mapping");
  const inner = text.slice(1, -1).trim();
  return splitTopLevel(inner).map((entry) => splitKeyValue(entry.trim()));
}

/** Splits `key: value` at the first colon that ends the key. */
export function splitKeyValue(entry: string): [string, string] {
  const match = /^([A-Za-z_][A-Za-z0-9_]*):(?:\s+(.*))?$/.exec(entry);
  if (!match) throw new UnsupportedYamlError("key");
  return [match[1] ?? "", match[2] ?? ""];
}

/** Serializes a scalar or list of scalars in flow style; strings are quoted unless clearly plain. */
export function formatScalar(value: unknown): string {
  if (value === null || value === undefined) return "null";
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return `[${value.map(formatScalar).join(", ")}]`;
  if (typeof value !== "string") throw new UnsupportedYamlError("value type");
  const isPlain = PLAIN_SAFE.test(value) && !RESERVED.has(value.toLowerCase());
  return isPlain ? value : JSON.stringify(value);
}
