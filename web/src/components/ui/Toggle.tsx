import { cx } from "../../lib/cx";

interface ToggleProps {
  readonly label: string;
  readonly isOn: boolean;
  readonly onChange: (isOn: boolean) => void;
}

/** Switch with a visible label on the right. */
export function Toggle({ label, isOn, onChange }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={isOn}
      onClick={() => {
        onChange(!isOn);
      }}
      className="inline-flex items-center gap-3 text-body"
    >
      <span
        aria-hidden="true"
        className={cx(
          "relative h-6 w-10 rounded-full transition-colors",
          isOn ? "bg-success" : "bg-ink-3/60",
        )}
      >
        <span
          className={cx(
            "absolute top-0.5 left-0.5 size-5 rounded-full bg-white shadow-card transition-transform",
            isOn && "translate-x-4",
          )}
        />
      </span>
      {label}
    </button>
  );
}
