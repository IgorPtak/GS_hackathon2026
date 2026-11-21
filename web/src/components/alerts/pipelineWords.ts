import type { ChipTone } from "../ui/StatusChip";

/** Plain-language reading of the pipeline numbers for people who do not speak "p99". */
export interface PipelineWords {
  readonly headline: string;
  readonly detail: string;
  readonly tone: ChipTone;
  readonly chip: string;
}

interface PipelineNumbers {
  readonly p99Milliseconds: number | null;
  readonly lostTotal: number | null;
  readonly hasError: boolean;
}

// Above these, notifications feel late to the person on call.
const SLOW_MILLISECONDS = 3_000;
const DELAYED_MILLISECONDS = 10_000;

function describeSpeed(p99Milliseconds: number | null): string {
  if (p99Milliseconds === null)
    return "Quiet in the last minute. New alerts reach people right away.";
  if (p99Milliseconds < 1_000) return "People are notified in under a second.";
  const seconds = Math.round(p99Milliseconds / 1_000);
  return `People are notified within about ${String(seconds)} second${seconds === 1 ? "" : "s"}.`;
}

export function describePipeline({
  p99Milliseconds,
  lostTotal,
  hasError,
}: PipelineNumbers): PipelineWords {
  if (hasError) {
    return {
      headline: "Status unavailable",
      detail: "Beacon cannot read its health numbers right now. Alerts still flow.",
      tone: "warning",
      chip: "No data",
    };
  }
  if (p99Milliseconds === null && lostTotal === null) {
    return {
      headline: "Checking the pipeline…",
      detail: "Reading Beacon's health numbers.",
      tone: "neutral",
      chip: "Checking",
    };
  }
  const detail = describeSpeed(p99Milliseconds);
  const chip = lostTotal === null ? "Counting" : lostTotal > 0 ? "Some not sent" : "Nothing lost";
  if (lostTotal !== null && lostTotal > 0) {
    return {
      headline: "Some notifications could not be sent",
      detail: `${lostTotal.toLocaleString()} are parked for a retry. ${detail}`,
      tone: "critical",
      chip,
    };
  }
  if (p99Milliseconds !== null && p99Milliseconds >= DELAYED_MILLISECONDS) {
    return { headline: "Notifications are delayed", detail, tone: "warning", chip };
  }
  if (p99Milliseconds !== null && p99Milliseconds >= SLOW_MILLISECONDS) {
    return { headline: "Running a little slow", detail, tone: "warning", chip };
  }
  return {
    headline: "Everything is running smoothly",
    detail,
    tone: lostTotal === null ? "neutral" : "success",
    chip,
  };
}

/** The engineer's numbers, kept for the tooltip and the Insights screen. */
export function describeNumbers(rate: number | null, p99Milliseconds: number | null): string {
  const shownRate = rate === null ? "–" : rate >= 10 ? String(Math.round(rate)) : rate.toFixed(1);
  const shownP99 = p99Milliseconds === null ? "–" : String(Math.round(p99Milliseconds));
  return `${shownRate} events per second, 99% delivered within ${shownP99} ms`;
}
