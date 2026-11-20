type ClassPart = string | false | null | undefined;

/** Joins class names, skipping falsy parts. */
export function cx(...parts: readonly ClassPart[]): string {
  return parts.filter(Boolean).join(" ");
}
