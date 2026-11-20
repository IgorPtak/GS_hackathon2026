import { useCallback, useEffect, useRef, useState } from "react";

import type { PhoneMessage } from "../../api/types";
import { CallKeypad } from "./CallKeypad";
import { sendCallReply, type CallReplyOutcome } from "./sendCallReply";
import { useSpeech } from "./useSpeech";

function spokenText(message: PhoneMessage): string {
  const code = message.approval_code;
  if (!code) return message.text;
  const spaced = code.split("").join(" ");
  return `${message.text} To approve, enter code ${spaced}. To reject, press star.`;
}

function formatTimer(seconds: number): string {
  const m = Math.floor(seconds / 60);
  return `${String(m).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

interface ActiveCallProps {
  message: PhoneMessage;
  onHangUp: () => void;
}

/** Answered call: reads the message aloud, shows transcript, timer and keypad. */
export function ActiveCall({ message, onHangUp }: ActiveCallProps) {
  const { isSupported, speak, cancel } = useSpeech();
  const [seconds, setSeconds] = useState(0);
  const [digits, setDigits] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [result, setResult] = useState<CallReplyOutcome | null>(null);
  const sendingRef = useRef(false);
  const text = spokenText(message);

  useEffect(() => {
    speak(text);
  }, [speak, text]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSeconds((s) => s + 1);
    }, 1000);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const send = useCallback(
    async (reply: string) => {
      if (sendingRef.current) return;
      sendingRef.current = true;
      setIsSending(true);
      const outcome = await sendCallReply(message.recipient_id, reply);
      setResult(outcome);
      setDigits("");
      sendingRef.current = false;
      setIsSending(false);
    },
    [message.recipient_id],
  );

  const pressKey = useCallback(
    (key: string) => {
      if (sendingRef.current) return;
      if (key === "#") {
        speak(text);
      } else if (key === "*") {
        if (message.approval_code) {
          void send(`REJECT ${message.approval_code}`);
        } else {
          setResult({ message: "This call has no approval code to reject.", isOk: false });
        }
      } else {
        const next = digits + key;
        if (next.length >= 4) void send(`APPROVE ${next}`);
        else setDigits(next);
      }
    },
    [digits, message.approval_code, send, speak, text],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest("input, textarea, select")) return;
      if (/^[0-9*#]$/.test(event.key)) pressKey(event.key);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [pressKey]);

  return (
    <div className="flex h-full flex-col gap-2 overflow-y-auto">
      <div className="flex items-center justify-between text-xs text-slate-300">
        <span aria-label="Call duration" role="timer">
          {formatTimer(seconds)}
        </span>
        {!isSupported ? <span>Voice not supported in this browser</span> : null}
      </div>
      <p
        aria-label="Call transcript"
        className="max-h-24 overflow-y-auto rounded bg-slate-800 p-2 text-sm break-words text-white"
      >
        {text}
      </p>
      <p aria-label="Typed digits" className="h-7 text-center font-mono text-xl text-white">
        {digits === "" ? "" : digits.padEnd(4, "•")}
      </p>
      <CallKeypad disabled={isSending} onKey={pressKey} />
      {result ? (
        <p role="status" className={`text-sm ${result.isOk ? "text-green-300" : "text-amber-300"}`}>
          {result.message}
        </p>
      ) : null}
      <button
        type="button"
        aria-label="Hang up"
        onClick={() => {
          cancel();
          onHangUp();
        }}
        className="rounded-full bg-red-600 py-2 font-semibold text-white hover:bg-red-500"
      >
        Hang up
      </button>
    </div>
  );
}
