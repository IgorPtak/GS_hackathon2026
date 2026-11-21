import type { ConfigValidationError } from "../../api/types";

/** Server validation messages shown next to the field they belong to. */
export function FieldErrors({ errors }: { readonly errors: readonly ConfigValidationError[] }) {
  if (errors.length === 0) return null;
  return (
    <ul role="alert" className="mt-1 space-y-0.5 text-meta text-critical-ink">
      {errors.map((e, i) => (
        <li key={`${e.path}-${String(i)}`} className="break-words">
          {e.message} <span className="font-mono text-caption text-ink-2">({e.path})</span>
        </li>
      ))}
    </ul>
  );
}
