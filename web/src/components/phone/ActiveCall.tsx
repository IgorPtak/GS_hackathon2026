import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { PhoneMessage } from "../../api/types";
import { cx } from "../../lib/cx";
import { Icon } from "../ui/icons";
import { CallKeypad } from "./CallKeypad";
import { playKeypadTone } from "./playChime";
import { sendCallReply, type CallReplyOutcome } from "./sendCallReply";
import { buildCallScript } from "./speechScript";
import type { SpeechController } from "./useSpeech";

function formatTimer(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

interface ActiveCallProps {
  readonly message: PhoneMessage;
  readonly recipientName: string | null;
  readonly speech: SpeechController;
  readonly autoSpeak?: boolean;
  readonly onHangUp: () => void;
}

/** Answered call: speaks the escalation script, shows live timer, 4-dot entry, and iOS keypad. */
export function ActiveCall({
  message,
  recipientName,
  speech,
  autoSpeak = true,
  onHangUp,
}: ActiveCallProps) {
  const { isSupported, speakSentences, cancel } = speech;
  const [seconds, setSeconds] = useState(0);
  const [digits, setDigits] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [result, setResult] = useState<CallReplyOutcome | null>(null);
  const sendingRef = useRef(false);
  const script = useMemo(() => buildCallScript(message, recipientName), [message, recipientName]);

  // Decide once, when the call is picked up: the parent flips `autoSpeak` right after answering,
  // and voices loading later swap `speakSentences`; neither may cut the script off mid-sentence.
  const [shouldSpeakOnAnswer] = useState(autoSpeak);
  const speakRef = useRef(speakSentences);
  useEffect(() => {
    speakRef.current = speakSentences;
  });
  useEffect(() => {
    if (shouldSpeakOnAnswer) speakRef.current(script);
    return cancel;
  }, [shouldSpeakOnAnswer, cancel, script]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSeconds((value) => value + 1);
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
      playKeypadTone(key);
      if (key === "#") {
        speakSentences(script);
      } else if (key === "*") {
        if (message.approval_code) {
          void send(`REJECT ${message.approval_code}`);
        } else {
          setResult({ message: "This call has no approval code to reject.", isOk: false });
        }
      } else {
        setResult(null);
        const next = digits + key;
        if (next.length >= 4) {
          setDigits(next.slice(0, 4));
          void send(`APPROVE ${next.slice(0, 4)}`);
        } else {
          setDigits(next);
        }
      }
    },
    [digits, message.approval_code, script, send, speakSentences],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target;
      if (target instanceof HTMLElement && target.closest("input, textarea, select")) return;
      if (/^[0-9*#]$/.test(event.key)) {
        pressKey(event.key);
      } else if (event.key === "Backspace" && digits.length > 0) {
        setDigits((prev) => prev.slice(0, -1));
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [digits.length, pressKey]);

  return (
    <div className="phone-call-backdrop flex h-full flex-col justify-between px-5 pt-4 pb-5 text-white">
      <div className="text-center">
        <p className="text-[18px] leading-[22px] font-semibold tracking-tight text-white">
          Beacon alerts
        </p>
        <p aria-label="Call duration" role="timer" className="num mt-0.5 text-[13px] text-white/70">
          {formatTimer(seconds)}
        </p>
        {!isSupported ? (
          <p className="mt-1 text-[11px] text-white/55">Browser voice unavailable</p>
        ) : null}
      </div>

      <div className="flex min-h-[48px] flex-col items-center justify-center gap-2">
        {result ? (
          <p
            role="status"
            className={cx(
              "inline-flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12px] font-medium",
              result.isOk ? "bg-[#30d158]/24 text-[#9ff4b4]" : "bg-[#ff453a]/24 text-[#ffb1ac]",
            )}
          >
            <Icon name={result.isOk ? "check" : "alert"} size={14} />
            {result.message}
          </p>
        ) : (
          <div className="relative flex items-center justify-center">
            <div
              role="status"
              aria-label={
                digits.length > 0
                  ? `${String(digits.length)} of 4 digits entered`
                  : "Enter 4-digit approval code"
              }
              className="flex items-center gap-3.5"
            >
              {[0, 1, 2, 3].map((slot) => (
                <span
                  key={slot}
                  aria-hidden="true"
                  className={cx(
                    "size-3 rounded-full transition-colors",
                    slot < digits.length ? "bg-white" : "border border-white/40 bg-transparent",
                  )}
                />
              ))}
            </div>
            {digits.length > 0 ? (
              <button
                type="button"
                aria-label="Delete last digit"
                onClick={() => {
                  setDigits((prev) => prev.slice(0, -1));
                }}
                className="absolute -right-10 flex size-7 items-center justify-center rounded-full text-white/70 hover:bg-white/12 hover:text-white"
              >
                <Icon name="backspace" size={16} />
              </button>
            ) : null}
          </div>
        )}
      </div>

      <CallKeypad disabled={isSending} onKey={pressKey} />

      <div className="flex justify-center pt-1">
        <button
          type="button"
          aria-label="End call"
          onClick={() => {
            cancel();
            onHangUp();
          }}
          className="flex size-[58px] items-center justify-center rounded-full bg-[#ff3b30] text-white shadow-lg transition-transform hover:bg-[#ff5147] active:scale-95"
        >
          <Icon name="phoneOff" size={24} />
        </button>
      </div>
    </div>
  );
}
