import { useState } from "react";

import type { PhoneMessage } from "../../api/types";
import { ActiveCall } from "./ActiveCall";
import { useRingTone } from "./useRingTone";

interface IncomingCallScreenProps {
  message: PhoneMessage;
  /** Team name or alert id shown as the caller. */
  callerLabel: string;
  /** Called when the call ends; `answered` tells whether it was picked up. */
  onClose: (answered: boolean) => void;
}

/** Full-screen call overlay inside the phone frame: ringing, then the answered call. */
export function IncomingCallScreen({ message, callerLabel, onClose }: IncomingCallScreenProps) {
  const [isAnswered, setIsAnswered] = useState(false);
  const { isMuted, toggleMute } = useRingTone(!isAnswered);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Incoming call"
      className="absolute inset-0 z-10 flex flex-col bg-slate-900 p-4 text-white"
    >
      {isAnswered ? (
        <ActiveCall
          message={message}
          onHangUp={() => {
            onClose(true);
          }}
        />
      ) : (
        <>
          <div className="flex justify-end">
            <button
              type="button"
              aria-pressed={isMuted}
              aria-label={isMuted ? "Unmute ring tone" : "Mute ring tone"}
              onClick={toggleMute}
              className="rounded border border-slate-500 px-2 py-1 text-xs"
            >
              {isMuted ? "Unmute" : "Mute"}
            </button>
          </div>
          <div className="flex flex-1 flex-col items-center justify-center gap-1 text-center">
            <p className="text-xs tracking-wide text-slate-400 uppercase">Incoming call</p>
            <p className="text-lg font-semibold break-words">Alerting — {callerLabel}</p>
          </div>
          <div className="flex justify-around pb-4">
            <button
              type="button"
              aria-label="Decline call"
              onClick={() => {
                onClose(false);
              }}
              className="animate-pulse rounded-full bg-red-600 px-5 py-3 font-semibold hover:bg-red-500"
            >
              Decline
            </button>
            <button
              type="button"
              aria-label="Answer call"
              onClick={() => {
                setIsAnswered(true);
              }}
              className="animate-pulse rounded-full bg-green-600 px-5 py-3 font-semibold hover:bg-green-500"
            >
              Answer
            </button>
          </div>
        </>
      )}
    </div>
  );
}
