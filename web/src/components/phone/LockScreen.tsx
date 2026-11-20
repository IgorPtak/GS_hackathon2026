import { useEffect, useState } from "react";

import type { PhoneMessage, Recipient } from "../../api/types";
import { Icon } from "../ui/icons";
import { Spinner } from "../ui/Spinner";
import { PhoneMessageBubble } from "./PhoneMessageBubble";

interface LockScreenProps {
  readonly messages: readonly PhoneMessage[];
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly onReload: () => void;
  readonly answeredIds: readonly string[];
  readonly activeCallId: string | null;
  readonly recipientName: string | null;
  readonly isAudioUnlocked: boolean;
  readonly onOpenCall: (message: PhoneMessage) => void;
  readonly isFullScreen?: boolean;
  readonly recipients?: readonly Recipient[];
  readonly selectedRecipientId?: string | null;
  readonly onSelectRecipient?: (id: string) => void;
}

function useLiveClock(): { readonly time: string; readonly date: string } {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(new Date());
    }, 10_000);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const time = new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(now);
  const date = new Intl.DateTimeFormat("en-GB", {
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(now);

  return { time, date };
}

/** iOS-inspired Lock Screen: thin big clock, date, and stacked translucent Beacon notifications. */
export function LockScreen({
  messages,
  isLoading,
  error,
  onReload,
  answeredIds,
  activeCallId,
  recipientName,
  isAudioUnlocked,
  onOpenCall,
  isFullScreen = false,
  recipients = [],
  selectedRecipientId = null,
  onSelectRecipient,
}: LockScreenProps) {
  const { time, date } = useLiveClock();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const firstName = recipientName?.trim().split(/\s+/)[0] ?? "this person";
  const newestFirst = [...messages].reverse();

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 px-5 pt-4 pb-5 text-center">
        <p className="text-[13px] font-medium tracking-tight text-white/85">{date}</p>
        <p
          aria-label="Current time"
          className="num mt-0.5 text-[56px] leading-[60px] font-extralight tracking-[-0.03em] text-white"
        >
          {time}
        </p>
      </div>

      <div className="phone-scroll min-h-0 flex-1 overflow-y-auto px-3.5 pb-3">
        {isLoading ? (
          <div className="flex justify-center py-8 text-white/70">
            <Spinner size={20} label="Loading notifications" />
          </div>
        ) : null}

        {error ? (
          <div
            role="alert"
            className="phone-notification rounded-[20px] p-3.5 text-center text-[13px]"
          >
            <p className="text-[#ff9f99]">Could not load messages ({error}).</p>
            <button
              type="button"
              onClick={onReload}
              className="mt-2 rounded-full bg-white/15 px-3 py-1 text-[12px] font-medium text-white hover:bg-white/25"
            >
              Retry
            </button>
          </div>
        ) : null}

        {!isLoading && !error && newestFirst.length === 0 ? (
          <div className="phone-notification mt-2 rounded-[20px] px-4 py-4 text-center">
            <p className="text-[13px] leading-[18px] text-white/80">
              No notifications yet. Alerts and approvals for {firstName} will appear here.
            </p>
          </div>
        ) : null}

        {newestFirst.length > 0 ? (
          <ul aria-label="Notifications" className="flex flex-col gap-2.5">
            {newestFirst.map((message) => (
              <PhoneMessageBubble
                key={message.id}
                message={message}
                isExpanded={expandedId === message.id}
                isMissed={
                  message.channel_type === "phone" &&
                  message.id !== activeCallId &&
                  !answeredIds.includes(message.id)
                }
                onToggle={() => {
                  setExpandedId((prev) => (prev === message.id ? null : message.id));
                }}
                onOpenCall={
                  message.channel_type === "phone"
                    ? () => {
                        onOpenCall(message);
                      }
                    : undefined
                }
              />
            ))}
          </ul>
        ) : null}
      </div>

      <div className="flex shrink-0 flex-col items-center gap-2 px-4 pt-1 pb-2">
        {!isAudioUnlocked ? (
          <p className="inline-flex items-center gap-1.5 rounded-full bg-white/12 px-3 py-1 text-[11px] font-medium text-white/80 backdrop-blur-md">
            <Icon name="volume" size={12} />
            Click anywhere to enable sound
          </p>
        ) : null}

        {isFullScreen && recipients.length > 1 && selectedRecipientId && onSelectRecipient ? (
          <label className="relative inline-flex items-center">
            <span className="sr-only">Recipient</span>
            <select
              value={selectedRecipientId}
              onChange={(event) => {
                onSelectRecipient(event.target.value);
              }}
              className="h-8 appearance-none rounded-full border border-white/15 bg-white/12 pr-7 pl-3.5 text-[12px] font-medium text-white backdrop-blur-md"
            >
              {recipients.map((recipient) => (
                <option key={recipient.id} value={recipient.id} className="bg-[#1c1c1e] text-white">
                  {recipient.display_name}
                </option>
              ))}
            </select>
            <Icon
              name="chevron"
              size={12}
              className="pointer-events-none absolute right-2.5 text-white/70"
            />
          </label>
        ) : null}
      </div>
    </div>
  );
}
