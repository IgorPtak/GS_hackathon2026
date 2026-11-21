import { cx } from "../../lib/cx";

/** One second of history; `null` slots have not been filled yet. */
export interface PulseSample {
  readonly rate: number;
  /** True when a delivery was dead-lettered during this second. */
  readonly hasLoss: boolean;
}

interface PulseBarsProps {
  /** Newest sample last; bars fill in from the right. */
  readonly samples: readonly PulseSample[];
  /** How many one-second slots to draw. */
  readonly slots?: number;
  readonly className?: string;
}

const MIN_BAR_PERCENT = 6;

/** Thin rounded bars, one per second. Decorative: the numbers beside it carry the meaning. */
export function PulseBars({ samples, slots = 60, className }: PulseBarsProps) {
  const visible = samples.slice(-slots);
  const peak = Math.max(1, ...visible.map((sample) => sample.rate));
  const padding = slots - visible.length;
  return (
    <div
      aria-hidden="true"
      className={cx("relative flex h-14 items-end gap-0.5 sm:gap-[3px]", className)}
      data-testid="pulse-bars"
    >
      {/* A calm baseline: quiet seconds sit on it instead of drawing a dashed row of dots. */}
      <span className="absolute inset-x-0 bottom-0 h-px rounded-full bg-hairline" />
      {Array.from({ length: padding }, (_, index) => (
        <span key={`empty-${String(index)}`} className="min-w-px flex-1" />
      ))}
      {visible.map((sample, index) => {
        const isQuiet = sample.rate <= 0 && !sample.hasLoss;
        return (
          <span
            key={index}
            style={{
              height: isQuiet
                ? "0%"
                : `${String(Math.max(MIN_BAR_PERCENT, (sample.rate / peak) * 100))}%`,
            }}
            className={cx(
              "relative min-w-px flex-1 rounded-full transition-[height] duration-500",
              sample.hasLoss ? "bg-critical" : "bg-ink/80",
            )}
          />
        );
      })}
    </div>
  );
}
