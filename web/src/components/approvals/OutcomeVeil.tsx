import { cx } from "../../lib/cx";
import { Icon } from "../ui/icons";

interface OutcomeVeilProps {
  readonly isPositive: boolean;
  readonly title: string;
  readonly detail: string;
}

/** Covers a decided card with its outcome for a moment, so the change is seen, not missed. */
export function OutcomeVeil({ isPositive, title, detail }: OutcomeVeilProps) {
  return (
    <div
      role="status"
      className="absolute inset-0 z-10 flex animate-fade-in items-center justify-center gap-3 rounded-card bg-card/85 backdrop-blur-[2px]"
    >
      <span
        className={cx(
          "flex size-10 animate-pop items-center justify-center rounded-full",
          isPositive ? "bg-success text-white" : "bg-fill text-ink-2",
        )}
      >
        <Icon name={isPositive ? "check" : "cross"} size={20} strokeWidth={2.6} />
      </span>
      <span className="text-row font-semibold">
        {title}
        <span className="block text-meta font-normal text-ink-2">{detail}</span>
      </span>
    </div>
  );
}
