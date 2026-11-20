import { useState } from "react";

import { apiClient } from "../../api/client";

interface PhoneReplyBoxProps {
  recipientId: string;
  /** Approval code of the newest message, offered as quick APPROVE / REJECT buttons. */
  approvalCode: string | null;
}

/** Reply field plus quick buttons; shows the PhoneReplyResult message. */
export function PhoneReplyBox({ recipientId, approvalCode }: PhoneReplyBoxProps) {
  const [text, setText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [result, setResult] = useState<{ message: string; isOk: boolean } | null>(null);

  async function send(reply: string) {
    const trimmed = reply.trim();
    if (trimmed === "") return;
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
              : `Could not send the reply (API error ${String(response.status)}).`,
          isOk: false,
        });
      }
    } catch (e) {
      setResult({
        message: `Could not send the reply: ${e instanceof Error ? e.message : "API unreachable"}.`,
        isOk: false,
      });
    } finally {
      setIsSending(false);
    }
  }

  return (
    <div className="border-t border-slate-200 p-3">
      {approvalCode ? (
        <div className="mb-2 flex flex-wrap gap-2">
          {(["APPROVE", "REJECT"] as const).map((verb) => (
            <button
              key={verb}
              type="button"
              disabled={isSending}
              onClick={() => {
                void send(`${verb} ${approvalCode}`);
              }}
              className="rounded border border-slate-400 px-2 py-1 font-mono text-xs disabled:opacity-40"
            >
              {verb} {approvalCode}
            </button>
          ))}
        </div>
      ) : null}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void send(text);
        }}
      >
        <input
          type="text"
          value={text}
          aria-label="Reply"
          placeholder="APPROVE 1234"
          onChange={(event) => {
            setText(event.target.value);
          }}
          className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-sm"
        />
        <button
          type="submit"
          disabled={isSending || text.trim() === ""}
          className="rounded bg-slate-800 px-3 py-1 text-sm text-white disabled:opacity-40"
        >
          {isSending ? "Sending..." : "Send"}
        </button>
      </form>
      {result ? (
        <p
          role="status"
          className={`mt-2 text-sm ${result.isOk ? "text-green-800" : "text-amber-800"}`}
        >
          {result.message}
        </p>
      ) : null}
    </div>
  );
}
