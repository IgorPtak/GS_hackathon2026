import { cx } from "../../lib/cx";

interface SparklineProps {
  readonly values: readonly (number | null)[];
  readonly tone?: "default" | "success" | "critical";
  readonly height?: number;
  readonly className?: string;
}

const TONE_CLASS = {
  default: "text-ink-2",
  success: "text-success",
  critical: "text-critical",
} as const;

const VIEW_W = 120;
const VIEW_H = 32;
const PAD_Y = 4;

function buildPoints(values: readonly number[]): string {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const usableH = VIEW_H - PAD_Y * 2;
  const stepX = values.length > 1 ? VIEW_W / (values.length - 1) : VIEW_W;

  return values
    .map((val, i) => {
      const x = values.length === 1 ? VIEW_W : i * stepX;
      const ratio = span === 0 ? 0.15 : (val - min) / span;
      const y = VIEW_H - PAD_Y - ratio * usableH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

/** Tiny decorative SVG sparkline built from client-side polling history. */
export function Sparkline({ values, tone = "default", height = 28, className }: SparklineProps) {
  const numeric = values.filter((v): v is number => v !== null && Number.isFinite(v));
  const baselineY = VIEW_H - PAD_Y;

  if (numeric.length < 2) {
    const singleY = numeric.length === 1 ? baselineY - 2 : baselineY;
    return (
      <svg
        aria-hidden="true"
        viewBox={`0 0 ${String(VIEW_W)} ${String(VIEW_H)}`}
        preserveAspectRatio="none"
        style={{ height }}
        className={cx("w-full overflow-visible", TONE_CLASS[tone], className)}
      >
        <line
          x1="0"
          y1={singleY}
          x2={VIEW_W}
          y2={singleY}
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeOpacity={numeric.length === 1 ? 0.55 : 0.18}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    );
  }

  const linePoints = buildPoints(numeric);
  const areaPoints = `0,${String(VIEW_H)} ${linePoints} ${String(VIEW_W)},${String(VIEW_H)}`;

  return (
    <svg
      aria-hidden="true"
      viewBox={`0 0 ${String(VIEW_W)} ${String(VIEW_H)}`}
      preserveAspectRatio="none"
      style={{ height }}
      className={cx("w-full overflow-visible", TONE_CLASS[tone], className)}
    >
      <polygon points={areaPoints} fill="currentColor" fillOpacity="0.09" />
      <polyline
        points={linePoints}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
