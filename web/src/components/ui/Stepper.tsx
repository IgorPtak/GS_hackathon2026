import { cx } from "../../lib/cx";
import { Icon } from "./icons";

interface StepperProps {
  readonly label: string;
  readonly steps: readonly string[];
  /** 1-based number of the current step. */
  readonly current: number;
  /** Finished steps become links back; future steps are plain text, never buttons. */
  readonly onBack?: (step: number) => void;
}

/** Progress through a short flow: done (tick, can go back), current (dark), next (quiet). */
export function Stepper({ label, steps, current, onBack }: StepperProps) {
  return (
    <nav aria-label={label}>
      <ol className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {steps.map((name, index) => {
          const number = index + 1;
          const isDone = number < current;
          const isCurrent = number === current;
          const content = (
            <>
              <span
                className={cx(
                  "flex size-7 shrink-0 items-center justify-center rounded-full text-meta font-semibold transition-colors duration-300",
                  isDone && "bg-success/15 text-success-ink",
                  isCurrent && "bg-ink text-window",
                  !isDone && !isCurrent && "border border-hairline text-ink-3",
                )}
              >
                {isDone ? <Icon name="check" size={14} strokeWidth={2.6} /> : number}
              </span>
              <span
                className={cx(
                  "text-body whitespace-nowrap transition-colors duration-300",
                  isCurrent ? "font-semibold text-ink" : isDone ? "text-ink-2" : "text-ink-3",
                )}
              >
                {name}
              </span>
            </>
          );
          return (
            <li
              key={name}
              aria-current={isCurrent ? "step" : undefined}
              className="flex items-center gap-3"
            >
              {index > 0 ? (
                <span
                  aria-hidden="true"
                  className={cx(
                    "h-px w-8 transition-colors duration-300 max-sm:w-4",
                    number <= current ? "bg-ink-3" : "bg-hairline",
                  )}
                />
              ) : null}
              {isDone && onBack ? (
                <button
                  type="button"
                  onClick={() => {
                    onBack(number);
                  }}
                  className="-mx-1.5 flex items-center gap-2.5 rounded-full px-1.5 py-1 transition-colors hover:bg-fill"
                >
                  {content}
                  <span className="sr-only">(done, go back)</span>
                </button>
              ) : (
                <span className="flex items-center gap-2.5 py-1">{content}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
