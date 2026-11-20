import type { ConfigValidationError } from "../../api/types";

interface ValidationErrorListProps {
  readonly errors: readonly ConfigValidationError[];
  readonly isChecking: boolean;
  readonly isValid: boolean;
  readonly requestError: string | null;
}

/** Validation status under the editor; errors are listed by dot path. */
export function ValidationErrorList({
  errors,
  isChecking,
  isValid,
  requestError,
}: ValidationErrorListProps) {
  if (requestError) {
    return (
      <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
        {requestError}
      </p>
    );
  }
  if (errors.length > 0) {
    return (
      <ul role="alert" className="space-y-1 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
        {errors.map((error, index) => (
          <li key={`${error.path}-${String(index)}`} className="break-words">
            <code className="font-mono font-semibold">
              {error.path === "" ? "(root)" : error.path}
            </code>
            : {error.message}
          </li>
        ))}
      </ul>
    );
  }
  if (isChecking) return <p className="text-sm text-slate-500">Validating...</p>;
  return isValid ? <p className="text-sm text-green-700">Rule is valid</p> : null;
}
