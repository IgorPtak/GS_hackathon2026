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

/** Reads ErrorResponse.details from a failed response body, if present. */
export function detailsFromBody(body: unknown): ConfigValidationError[] {
  if (typeof body !== "object" || body === null || !("details" in body)) return [];
  const details = (body as { details?: unknown }).details;
  if (!Array.isArray(details)) return [];
  return details.filter(
    (item): item is ConfigValidationError =>
      typeof item === "object" &&
      item !== null &&
      typeof (item as { path?: unknown }).path === "string" &&
      typeof (item as { message?: unknown }).message === "string",
  );
}

export function messageFromBody(body: unknown, fallback: string): string {
  if (typeof body === "object" && body !== null && "message" in body) {
    const message = (body as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return fallback;
}
