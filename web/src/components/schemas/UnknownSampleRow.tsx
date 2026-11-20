import type { UnknownSchemaSample } from "../../api/types";
import { formatRelativeTime } from "../alerts/alertFormat";
import { Avatar } from "../ui/Avatar";
import { Button } from "../ui/Button";
import { CountBadge } from "../ui/CountBadge";

const PREVIEW_FIELDS = 4;

/** "evt: payment.declined, lvl: WARN" from the top-level scalar fields of the sample. */
function previewFields(sample: UnknownSchemaSample): string {
  const pairs = Object.entries(sample.sample_event)
    .filter(([, v]) => typeof v === "string" || typeof v === "number" || typeof v === "boolean")
    .slice(0, PREVIEW_FIELDS)
    .map(([k, v]) => `${k}: ${String(v)}`);
  return pairs.length > 0 ? pairs.join(", ") : sample.key_paths.slice(0, PREVIEW_FIELDS).join(", ");
}

/** One unknown event shape: source, a preview of its fields, how often and when last seen. */
export function UnknownSampleRow({
  sample,
  onPick,
}: {
  readonly sample: UnknownSchemaSample;
  readonly onPick: () => void;
}) {
  return (
    <li className="flex items-center gap-4 px-5 py-4 max-sm:flex-wrap">
      <Avatar name={sample.source_id} size="lg" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-row font-semibold">{sample.source_id}</p>
          {sample.event_count > 1 ? <CountBadge count={sample.event_count} /> : null}
        </div>
        <p className="line-clamp-2 font-mono text-meta break-words text-ink-2">
          {previewFields(sample)}
        </p>
      </div>
      <time dateTime={sample.last_seen} className="num shrink-0 text-meta text-ink-2">
        {formatRelativeTime(sample.last_seen)}
      </time>
      <Button variant="secondary" icon="sparkle" onClick={onPick}>
        Map this event
      </Button>
    </li>
  );
}
