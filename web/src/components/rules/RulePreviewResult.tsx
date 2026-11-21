import type { RulePreview } from "../../api/types";
import { channelWord } from "../recipients/preferenceSentence";
import { Avatar } from "../ui/Avatar";
import { CountBadge } from "../ui/CountBadge";
import { SeverityDot } from "../ui/SeverityDot";
import { StatusChip } from "../ui/StatusChip";

const SAMPLE_LIMIT = 4;

const WINDOW_WORDS: Record<string, string> = {
  "15m": "15 minutes",
  "1h": "hour",
  "6h": "6 hours",
  "24h": "24 hours",
};

function plural(count: number, noun: string): string {
  return `${String(count)} ${noun}${count === 1 ? "" : "s"}`;
}

/** The big plain sentence that leads the preview. */
function previewSentence(preview: RulePreview, window: string): string {
  const sent = preview.deliveries.reduce((total, d) => total + d.count, 0);
  const span = `In the last ${WINDOW_WORDS[window] ?? window}`;
  if (preview.alerts_created === 0) return `${span} this rule would not have created any alerts.`;
  return `${span} this rule would have created ${plural(preview.alerts_created, "alert")} and sent ${plural(sent, "message")}.`;
}

function DeliveriesPerPerson({
  preview,
  names,
}: {
  readonly preview: RulePreview;
  readonly names: Readonly<Record<string, string>>;
}) {
  const people = new Map<string, { channel: string; count: number }[]>();
  for (const d of preview.deliveries) {
    const key = d.recipient_id ?? "";
    people.set(key, [...(people.get(key) ?? []), { channel: d.channel_id, count: d.count }]);
  }
  if (people.size === 0) {
    return <p className="text-body text-ink-2">No messages would have been sent.</p>;
  }
  return (
    <ul className="space-y-2">
      {[...people].map(([id, channels]) => {
        const name = id === "" ? "Everyone on duty" : (names[id] ?? id);
        return (
          <li
            key={id}
            className="flex flex-wrap items-center gap-3 rounded-tile bg-panel px-4 py-3"
          >
            <Avatar name={name} size="sm" />
            <span className="min-w-0 flex-1 text-body font-medium">{name}</span>
            <span className="flex flex-wrap gap-1.5">
              {channels.map((c) => (
                <StatusChip key={c.channel}>
                  {channelWord(c.channel)} · {c.count}
                </StatusChip>
              ))}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/** Sentence, sample alerts as mini rows, and messages per person and channel. */
export function RulePreviewResult({
  preview,
  window,
  names,
}: {
  readonly preview: RulePreview;
  readonly window: string;
  readonly names: Readonly<Record<string, string>>;
}) {
  return (
    <div className="space-y-6">
      <div>
        <p className="text-card-title font-semibold tracking-tight text-balance">
          {previewSentence(preview, window)}
        </p>
        <p className="num mt-2 text-meta text-ink-2">
          {plural(preview.events_scanned, "event")} checked, {String(preview.events_matched)}{" "}
          matched, in {String(preview.duration_ms)} ms.
        </p>
      </div>
      {(preview.warnings ?? []).map((warning) => (
        <p
          key={warning}
          className="rounded-tile bg-warning/20 px-4 py-3 text-body text-warning-ink"
        >
          {warning}
        </p>
      ))}
      <section aria-label="Sample alerts" className="space-y-2">
        <h4 className="text-body font-semibold">Sample alerts</h4>
        {preview.sample_alerts.length === 0 ? (
          <p className="text-body text-ink-2">No alerts would have been created.</p>
        ) : (
          <ul className="space-y-2">
            {preview.sample_alerts.slice(0, SAMPLE_LIMIT).map((alert) => (
              <li
                key={alert.fingerprint}
                className="flex items-center gap-3 rounded-tile border border-hairline px-4 py-3"
              >
                <SeverityDot severity={alert.severity} />
                <span className="min-w-0 flex-1 truncate text-body">{alert.title}</span>
                {alert.is_group_summary ? (
                  <StatusChip tone="info">Group of {alert.member_count}</StatusChip>
                ) : null}
                {alert.count > 1 ? <CountBadge count={alert.count} /> : null}
              </li>
            ))}
          </ul>
        )}
        {preview.sample_alerts.length > SAMPLE_LIMIT ? (
          <p className="text-meta text-ink-2">
            and {String(preview.sample_alerts.length - SAMPLE_LIMIT)} more alerts like these
          </p>
        ) : null}
      </section>
      <section aria-label="Messages per person" className="space-y-2">
        <h4 className="text-body font-semibold">Who would be messaged</h4>
        <DeliveriesPerPerson preview={preview} names={names} />
      </section>
    </div>
  );
}
