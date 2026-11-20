import type { PhoneMessage } from "../../api/types";

/** Splits text around the approval code so it can be highlighted. */
function HighlightedText({ text, code }: { text: string; code: string | null }) {
  if (!code || !text.includes(code)) return <>{text}</>;
  const parts = text.split(code);
  return (
    <>
      {parts.map((part, i) => (
        <span key={i}>
          {i > 0 ? (
            <mark className="rounded bg-amber-200 px-1 font-mono font-semibold">{code}</mark>
          ) : null}
          {part}
        </span>
      ))}
    </>
  );
}

/** One SMS or call on the mock phone. */
export function PhoneMessageBubble({
  message,
  isMissed = false,
}: {
  message: PhoneMessage;
  isMissed?: boolean;
}) {
  const isCall = message.channel_type === "phone";
  return (
    <li className="rounded-2xl rounded-tl-sm bg-white p-3 text-sm shadow-sm">
      <div className="mb-1 flex items-center gap-2 text-xs text-slate-500">
        <span aria-hidden>{isCall ? "☎" : "✉"}</span>
        <span className="font-medium">{isCall ? (isMissed ? "Missed call" : "Call") : "SMS"}</span>
        <span>{new Date(message.at).toLocaleTimeString()}</span>
      </div>
      <p className="break-words whitespace-pre-wrap">
        <HighlightedText text={message.text} code={message.approval_code} />
      </p>
      {message.approval_code && !message.text.includes(message.approval_code) ? (
        <p className="mt-1 text-xs">
          Code{" "}
          <mark className="rounded bg-amber-200 px-1 font-mono font-semibold">
            {message.approval_code}
          </mark>
        </p>
      ) : null}
    </li>
  );
}
