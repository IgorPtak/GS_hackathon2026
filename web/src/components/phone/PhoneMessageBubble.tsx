import type { PhoneMessage } from "../../api/types";
import { PRODUCT_NAME } from "../../lib/brand";
import { cx } from "../../lib/cx";
import { BeaconLogo } from "../ui/BeaconLogo";
import { Icon } from "../ui/icons";
import { toBannerText } from "./messageText";
import { PhoneReplyBox } from "./PhoneReplyBox";

interface PhoneMessageBubbleProps {
  readonly message: PhoneMessage;
  readonly isExpanded: boolean;
  readonly isMissed?: boolean;
  readonly onToggle: () => void;
  readonly onOpenCall?: () => void;
}

function formatBannerTime(iso: string): string {
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return "";
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (diffSec < 60) return "now";
  if (diffSec < 3600) return `${String(Math.floor(diffSec / 60))}m ago`;
  return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
}

function HighlightedText({ text, code }: { text: string; code: string | null }) {
  if (!code || !text.includes(code)) return <>{text}</>;
  const parts = text.split(code);
  return (
    <>
      {parts.map((part, index) => (
        <span key={index}>
          {index > 0 ? (
            <mark className="rounded bg-white/20 px-1 py-0.5 font-medium text-white num">
              {code}
            </mark>
          ) : null}
          {part}
        </span>
      ))}
    </>
  );
}

const SEVERITY_TONE: Record<string, string> = {
  critical: "text-[#ff8a80]",
  error: "text-[#ffb366]",
  warning: "text-[#ffd966]",
};

function BannerBody({ message, isExpanded }: { message: PhoneMessage; isExpanded: boolean }) {
  const banner = toBannerText(message.text);
  return (
    <div className="text-[13px] leading-[18px] break-words">
      <p className={cx("font-semibold text-white", isExpanded ? "" : "line-clamp-1")}>
        {banner.severity ? (
          <span
            className={cx("mr-1.5 capitalize", SEVERITY_TONE[banner.severity] ?? "text-white/70")}
          >
            {banner.severity}
          </span>
        ) : null}
        {banner.title}
      </p>
      {banner.detail ? (
        <p className={cx("text-white/80", isExpanded ? "whitespace-pre-wrap" : "line-clamp-2")}>
          <HighlightedText text={banner.detail} code={message.approval_code} />
        </p>
      ) : null}
    </div>
  );
}

/** Stacked translucent iOS-style notification banner; tap to expand and reply. */
export function PhoneMessageBubble({
  message,
  isExpanded,
  isMissed = false,
  onToggle,
  onOpenCall,
}: PhoneMessageBubbleProps) {
  const isCall = message.channel_type === "phone";

  return (
    <li
      className={cx(
        "rounded-[20px] p-3 text-white transition-colors",
        isExpanded ? "phone-notification-expanded" : "phone-notification",
      )}
    >
      <button
        type="button"
        aria-expanded={isExpanded}
        onClick={onToggle}
        className="block w-full text-left"
      >
        <div className="mb-1 flex items-center justify-between gap-2">
          <span className="flex min-w-0 items-center gap-1.5">
            <span className="flex size-5 shrink-0 items-center justify-center rounded-[6px] bg-white/15 text-white">
              <BeaconLogo size={12} aria-hidden="true" />
            </span>
            <span className="truncate text-[12px] font-semibold text-white/95">{PRODUCT_NAME}</span>
            {isCall ? (
              <span className="text-[11px] font-medium text-white/60">
                {isMissed ? "Missed call" : "Call"}
              </span>
            ) : null}
          </span>
          <span className="num shrink-0 text-[11px] text-white/60">
            {formatBannerTime(message.at)}
          </span>
        </div>

        <BannerBody message={message} isExpanded={isExpanded} />
      </button>

      {isExpanded ? (
        <div>
          {isCall && onOpenCall ? (
            <div className="mt-2">
              <button
                type="button"
                onClick={onOpenCall}
                className="inline-flex items-center gap-1.5 rounded-full bg-white/14 px-3 py-1 text-[11px] font-medium text-white transition-colors hover:bg-white/22"
              >
                <Icon name="phone" size={12} />
                Open call keypad
              </button>
            </div>
          ) : null}
          <PhoneReplyBox
            key={message.id}
            recipientId={message.recipient_id}
            approvalCode={message.approval_code}
          />
        </div>
      ) : null}
    </li>
  );
}
