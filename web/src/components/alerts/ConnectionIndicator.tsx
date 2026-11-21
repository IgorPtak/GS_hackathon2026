import type { StreamStatus } from "../../hooks/useEventStream";

const LABELS: Record<StreamStatus, { readonly text: string; readonly dot: string }> = {
  idle: { text: "Live updates off", dot: "bg-ink-3" },
  connecting: { text: "Connecting...", dot: "bg-warning" },
  open: { text: "Live", dot: "bg-success" },
  retrying: { text: "Reconnecting...", dot: "bg-critical" },
};

/** Small dot + label showing whether the SSE stream is delivering live updates. */
export function ConnectionIndicator({ status }: { status: StreamStatus }) {
  const label = LABELS[status];
  return (
    <span role="status" className="inline-flex items-center gap-1.5 text-meta text-ink-2">
      <span aria-hidden className={`size-2 rounded-full ${label.dot}`} />
      {label.text}
    </span>
  );
}
