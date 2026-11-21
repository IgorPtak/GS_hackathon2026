import type { ConfigValidationError } from "../../api/types";
import { StatusChip } from "../ui/StatusChip";
import { friendlyMessage, humanPath } from "./ruleErrors";

interface ValidationErrorListProps {
  readonly errors: readonly ConfigValidationError[];
  readonly isChecking: boolean;
  readonly isValid: boolean;
  readonly requestError: string | null;
}

/** Validation status: problems named by where they are ("Condition 2, value"), or "Rule is valid". */
export function ValidationErrorList({
  errors,
  isChecking,
  isValid,
  requestError,
}: ValidationErrorListProps) {
  if (requestError) {
    return (
      <p role="alert" className="rounded-tile bg-critical/12 px-4 py-3 text-body text-critical-ink">
        {requestError}
      </p>
    );
  }
  if (errors.length > 0) {
    // Several paths can read the same once named in plain words; say each thing once.
    const lines = [
      ...new Map(
        errors.map((error) => {
          const label = humanPath(error.path);
          const text = friendlyMessage(error.path, error.message);
          return [`${label}\u0000${text}`, { label, text }] as const;
        }),
      ).values(),
    ];
    return (
      <ul
        role="alert"
        className="animate-fade-in space-y-1 rounded-tile bg-critical/12 px-4 py-3 text-body"
      >
        {lines.map(({ label, text }) => (
          <li key={`${label}-${text}`} className="break-words text-critical-ink">
            <span className="font-medium">{label}:</span> {text}
          </li>
        ))}
      </ul>
    );
  }
  if (isChecking) return <p className="text-meta text-ink-2">Checking the rule…</p>;
  return isValid ? (
    <StatusChip tone="success" icon="check">
      Rule is valid
    </StatusChip>
  ) : null;
}
