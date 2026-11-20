import type { AlertDetail } from "../../api/types";
import { Timeline } from "../ui/Timeline";
import { TimelineStep } from "../ui/TimelineStep";
import { buildAlertTimeline } from "./buildAlertTimeline";

function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** What happened to this alert, in plain words; new SSE rows tick in as the detail updates. */
export function AlertTimeline({ detail }: { detail: AlertDetail }) {
  const items = buildAlertTimeline(detail);
  return (
    <Timeline label="What happened">
      {items.map((item, index) => (
        <TimelineStep
          key={item.key}
          state={item.state}
          title={item.title}
          meta={formatClock(item.at)}
          isLast={index === items.length - 1}
        />
      ))}
    </Timeline>
  );
}
