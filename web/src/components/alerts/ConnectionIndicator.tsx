import type { StreamStatus } from "../../hooks/useEventStream";

const LABELS: Record<StreamStatus, { readonly text: string; readonly dot: string }> = {
  idle: { text: "Live updates off", dot: "bg-slate-300" },
  connecting: { text: "Connecting...", dot: "bg-amber-400" },
  open: { text: "Live", dot: "bg-green-500" },
  retrying: { text: "Reconnecting...", dot: "bg-red-500" },
};

/** Small dot + label showing whether the SSE stream is delivering live updates. */
export function ConnectionIndicator({ status }: { status: StreamStatus }) {
  const label = LABELS[status];
  return (
    <span role="status" className="inline-flex items-center gap-1.5 text-xs text-slate-600">
      <span aria-hidden className={`h-2 w-2 rounded-full ${label.dot}`} />
      {label.text}
    </span>
  );
}
