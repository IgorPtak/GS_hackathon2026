import { useState } from "react";

import { apiClient } from "../../api/client";

interface PhoneReplyBoxProps {
  readonly recipientId: string;
  readonly approvalCode: string | null;
}

/** Quick-reply chips and text field inside an expanded iOS-style notification banner. */
export function PhoneReplyBox({ recipientId, approvalCode }: PhoneReplyBoxProps) {
  const [text, setText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [result, setResult] = useState<{ readonly message: string; readonly isOk: boolean } | null>(
    null,
  );

  async function send(reply: string) {
    const trimmed = reply.trim();
    if (trimmed === "" || isSending) return;
    setIsSending(true);
    try {
      const { data, response } = await apiClient.POST("/api/v1/phone-simulator/replies", {
        body: { recipient_id: recipientId, text: trimmed },
      });
      if (data) {
        setResult({ message: data.message, isOk: data.is_understood });
        setText("");
      } else {
        setResult({
          message:
            response.status === 404 || response.status === 503
              ? "Replies are not available yet."
              : `Could not send reply (API error ${String(response.status)}).`,
          isOk: false,
        });
      }
    } catch (e) {
      setResult({
        message: `Could not send reply: ${e instanceof Error ? e.message : "API unreachable"}.`,
        isOk: false,
      });
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="mt-2.5 flex flex-col gap-2 border-t border-white/12 pt-2.5">
      <div className="flex flex-wrap gap-1.5">
        {approvalCode ? (
          <>
            <button
              type="button"
              disabled={isSending}
              onClick={() => {
                void send(`APPROVE ${approvalCode}`);
              }}
              className="rounded-full bg-[#30d158]/22 px-2.5 py-1 text-[11px] font-medium text-[#8ef0a6] transition-colors hover:bg-[#30d158]/32 disabled:opacity-40"
            >
              APPROVE {approvalCode}
            </button>
            <button
              type="button"
              disabled={isSending}
              onClick={() => {
                void send(`REJECT ${approvalCode}`);
              }}
              className="rounded-full bg-[#ff453a]/22 px-2.5 py-1 text-[11px] font-medium text-[#ff9f99] transition-colors hover:bg-[#ff453a]/32 disabled:opacity-40"
            >
              REJECT {approvalCode}
            </button>
          </>
        ) : null}
        <button
          type="button"
          disabled={isSending}
          onClick={() => {
            void send("ACK");
          }}
          className="rounded-full bg-white/14 px-2.5 py-1 text-[11px] font-medium text-white/90 transition-colors hover:bg-white/24 disabled:opacity-40"
        >
          ACK
        </button>
      </div>

      <form
        className="flex items-center gap-1.5"
        onSubmit={(event) => {
          event.preventDefault();
          void send(text);
        }}
      >
        <input
          type="text"
          value={text}
          aria-label="Reply to notification"
          placeholder={approvalCode ? `APPROVE ${approvalCode}` : "Reply ACK"}
          autoCorrect="off"
          autoCapitalize="none"
          spellCheck={false}
          onChange={(event) => {
            setText(event.target.value);
          }}
          className="h-8 min-w-0 flex-1 rounded-full border border-white/15 bg-white/10 px-3 text-[12px] text-white placeholder:text-white/45"
        />
        <button
          type="submit"
          disabled={isSending || text.trim() === ""}
          className="h-8 shrink-0 rounded-full bg-white px-3 text-[12px] font-semibold text-[#1d1d1f] transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          {isSending ? "..." : "Send"}
        </button>
      </form>

      {result ? (
        <p
          role="status"
          className={`text-[12px] leading-4 ${result.isOk ? "text-[#8ef0a6]" : "text-[#ffd479]"}`}
        >
          {result.message}
        </p>
      ) : null}
    </div>
  );
}
