import { cx } from "../../lib/cx";
import { Card } from "../ui/Card";
import { StatusChip } from "../ui/StatusChip";
import { Tooltip } from "../ui/Tooltip";
import { Sparkline } from "./Sparkline";

export type MetricTone = "default" | "success" | "critical";

interface MetricTileProps {
  readonly label: string;
  readonly value: string | null;
  readonly unit?: string;
  readonly sublabel?: string;
  readonly badge?: string;
  readonly tone?: MetricTone;
  readonly size?: "hero" | "compact";
  readonly history: readonly (number | null)[];
}

const VALUE_TONE: Record<MetricTone, string> = {
  default: "text-ink",
  success: "text-success-ink",
  critical: "text-critical-ink",
};

function MissingValue({ isHero }: { readonly isHero: boolean }) {
  return (
    <Tooltip label="No data yet" side="top">
      <span
        tabIndex={0}
        aria-label="No data yet"
        className={cx(
          "num inline-block cursor-help rounded font-semibold text-ink-3",
          isHero ? "text-hero" : "text-card-title",
        )}
      >
        —
      </span>
    </Tooltip>
  );
}

/** One telemetry card (hero 40 px or compact 22 px) with tabular numbers and a sparkline. */
export function MetricTile({
  label,
  value,
  unit,
  sublabel,
  badge,
  tone = "default",
  size = "compact",
  history,
}: MetricTileProps) {
  const isHero = size === "hero";
  return (
    <Card
      as="div"
      isPadded={false}
      className={cx(
        "flex flex-col justify-between gap-4",
        isHero ? "p-6" : "rounded-tile p-4 shadow-none",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <dt className={cx("font-medium text-ink-2", isHero ? "text-body" : "text-meta")}>
          {label}
        </dt>
        {badge ? (
          <StatusChip tone={tone === "critical" ? "critical" : "success"}>{badge}</StatusChip>
        ) : null}
      </div>

      <dd className="m-0">
        {value === null ? (
          <MissingValue isHero={isHero} />
        ) : (
          <div className="flex items-baseline gap-1.5">
            <span
              className={cx(
                "num font-semibold tracking-tight",
                isHero ? "text-hero" : "text-card-title",
                VALUE_TONE[tone],
              )}
            >
              {value}
            </span>
            {unit ? (
              <span className={cx("font-normal text-ink-2", isHero ? "text-body" : "text-meta")}>
                {unit}
              </span>
            ) : null}
          </div>
        )}
        {sublabel ? <p className="num mt-1 text-meta text-ink-2">{sublabel}</p> : null}
      </dd>

      <Sparkline values={history} tone={tone} height={isHero ? 34 : 24} />
    </Card>
  );
}
