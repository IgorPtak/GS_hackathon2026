import type { ConfigValidationError } from "../../api/types";

/** Server validation messages shown next to the field they belong to. */
export function FieldErrors({ errors }: { readonly errors: readonly ConfigValidationError[] }) {
  if (errors.length === 0) return null;
  return (
    <ul role="alert" className="text-xs text-red-700">
      {errors.map((e, i) => (
        <li key={`${e.path}-${String(i)}`} className="break-words">
          <code className="font-mono">{e.path}</code>: {e.message}
        </li>
      ))}
    </ul>
  );
}
