import { useId, type ReactNode } from "react";

interface ControlProps {
  readonly id: string;
  readonly "aria-describedby": string | undefined;
  readonly "aria-invalid": boolean;
}

interface FieldProps {
  readonly label: string;
  readonly help?: string;
  /** Inline error, e.g. the message for one API validation path. */
  readonly error?: string | null;
  /** Receives the id and aria attributes to spread on the control. */
  readonly children: (control: ControlProps) => ReactNode;
}

/** Label, control, help text and inline error wired together with ids. */
export function Field({ label, help, error, children }: FieldProps) {
  const id = useId();
  const helpId = `${id}-help`;
  const errorId = `${id}-error`;
  const describedBy = [help ? helpId : null, error ? errorId : null].filter(Boolean).join(" ");

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-meta font-medium text-ink">
        {label}
      </label>
      {children({
        id,
        "aria-describedby": describedBy || undefined,
        "aria-invalid": Boolean(error),
      })}
      {help ? (
        <p id={helpId} className="text-meta text-ink-2">
          {help}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} role="alert" className="text-meta text-critical-ink">
          {error}
        </p>
      ) : null}
    </div>
  );
}
