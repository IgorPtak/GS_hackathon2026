import type { ReactNode } from "react";

import { cx } from "../../lib/cx";
import { Icon } from "./icons";
import { Spinner } from "./Spinner";

export type StepState = "pending" | "running" | "done" | "failed" | "skipped";

const STATE_WORDS: Record<StepState, string> = {
  pending: "Pending",
  running: "In progress",
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

function StepMarker({ state }: { state: StepState }) {
  const base =
    "flex size-6 items-center justify-center rounded-full transition-colors duration-200";
  if (state === "done") {
    return (
      <span className={cx(base, "bg-success text-white")}>
        <Icon name="check" size={14} strokeWidth={2.6} />
      </span>
    );
  }
  if (state === "failed") {
    return (
      <span className={cx(base, "bg-critical text-white")}>
        <Icon name="cross" size={13} strokeWidth={2.6} />
      </span>
    );
  }
  if (state === "running") {
    return (
      <span className={cx(base, "bg-accent/15 text-accent-ink")}>
        <Spinner size={14} label="" />
      </span>
    );
  }
  return (
    <span
      className={cx(
        base,
        "border-[1.5px]",
        state === "skipped" ? "border-hairline bg-fill" : "border-dashed border-ink-3",
      )}
    />
  );
}

interface TimelineStepProps {
  readonly state: StepState;
  readonly title: string;
  /** Right-aligned meta such as a relative time. */
  readonly meta?: string;
  /** Extra detail under the title. */
  readonly children?: ReactNode;
  readonly isLast?: boolean;
}

/** One plain-language step: "Emailed Anna". The state is also exposed as text. */
export function TimelineStep({ state, title, meta, children, isLast = false }: TimelineStepProps) {
  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {isLast ? null : (
        <span aria-hidden="true" className="absolute top-7 bottom-1 left-3 w-px bg-hairline" />
      )}
      <StepMarker state={state} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <p
            className={cx(
              "text-body font-medium",
              state === "pending" || state === "skipped" ? "text-ink-2" : "text-ink",
            )}
          >
            {title}
            <span className="sr-only"> ({STATE_WORDS[state]})</span>
          </p>
          {meta ? <span className="num shrink-0 text-meta text-ink-2">{meta}</span> : null}
        </div>
        {children ? <div className="mt-0.5 text-meta text-ink-2">{children}</div> : null}
      </div>
    </li>
  );
}
