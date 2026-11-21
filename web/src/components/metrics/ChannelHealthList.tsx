import { cx } from "../../lib/cx";
import { Icon, type IconName } from "../ui/icons";
import { Skeleton } from "../ui/Skeleton";
import type { ChannelHealth } from "./useChannelHealth";

const TYPE_WORDS: Record<ChannelHealth["channel_type"], { name: string; icon: IconName }> = {
  ui: { name: "Beacon inbox", icon: "inbox" },
  email: { name: "Email", icon: "send" },
  sms: { name: "Text messages", icon: "bell" },
  phone: { name: "Phone calls", icon: "phone" },
  webhook: { name: "Webhook", icon: "connect" },
};

function channelName(channel: ChannelHealth): string {
  if (channel.channel_type !== "webhook") return TYPE_WORDS[channel.channel_type].name;
  const words = channel.channel_id.split("-").join(" ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function since(iso: string | null | undefined): string {
  if (!iso) return "";
  const seconds = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  if (seconds < 60) return `${String(seconds)} s`;
  return `${String(Math.round(seconds / 60))} min`;
}

/** Status words a non-engineer can read: sending, paused (and why that is safe), or testing. */
function describe(channel: ChannelHealth): { label: string; detail: string; tone: string } {
  const waiting = channel.waiting_deliveries;
  const queue =
    waiting === 0 ? "Nothing waiting" : `${waiting.toLocaleString()} waiting, none lost`;
  if (channel.state === "open") {
    return {
      label: "Paused",
      detail: `Failed ${String(channel.failures)} times in a row, paused ${since(channel.opened_at)} ago. ${queue}.`,
      tone: "critical",
    };
  }
  if (channel.state === "half_open") {
    return {
      label: "Checking",
      detail: `Trying one message to see if it is back. ${queue}.`,
      tone: "warning",
    };
  }
  return { label: "Sending", detail: `${queue}.`, tone: "success" };
}

/**
 * One tile per channel from its circuit breaker. When a provider fails, Beacon pauses that
 * channel and keeps the messages; this is where that is visible.
 */
export function ChannelHealthList({
  channels,
  error,
}: {
  readonly channels: readonly ChannelHealth[] | null;
  readonly error: string | null;
}) {
  return (
    <section aria-labelledby="channels-heading" className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="channels-heading" className="text-row font-semibold text-ink">
          Channels
        </h2>
        {error ? <span className="text-meta text-warning-ink">{error}. Retrying.</span> : null}
      </div>
      {channels === null ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
          {[0, 1, 2].map((key) => (
            <Skeleton key={key} className="h-[104px] rounded-tile" />
          ))}
        </div>
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {channels.map((channel) => {
            const words = describe(channel);
            return (
              <li
                key={channel.channel_id}
                className={cx(
                  "flex items-start gap-3.5 rounded-tile border bg-card p-4 shadow-card transition-[border-color,background-color] duration-500",
                  words.tone === "critical"
                    ? "border-critical/35 bg-critical/5"
                    : words.tone === "warning"
                      ? "border-warning/50"
                      : "border-hairline",
                )}
              >
                <span
                  className={cx(
                    "flex size-10 shrink-0 items-center justify-center rounded-full transition-colors duration-500",
                    words.tone === "critical"
                      ? "bg-critical/12 text-critical-ink"
                      : words.tone === "warning"
                        ? "bg-warning/20 text-warning-ink"
                        : "bg-fill text-ink",
                  )}
                >
                  <Icon
                    name={
                      channel.state === "open" ? "signalOff" : TYPE_WORDS[channel.channel_type].icon
                    }
                    size={19}
                  />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <p className="truncate text-body font-semibold">{channelName(channel)}</p>
                    <span
                      className={cx(
                        "inline-flex items-center gap-1.5 text-meta font-medium",
                        words.tone === "critical"
                          ? "text-critical-ink"
                          : words.tone === "warning"
                            ? "text-warning-ink"
                            : "text-success-ink",
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className={cx(
                          "size-2 rounded-full",
                          words.tone === "critical"
                            ? "animate-pulse bg-critical"
                            : words.tone === "warning"
                              ? "animate-pulse bg-warning"
                              : "bg-success",
                        )}
                      />
                      {words.label}
                    </span>
                  </div>
                  <p className="mt-1 text-meta text-ink-2">{words.detail}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
