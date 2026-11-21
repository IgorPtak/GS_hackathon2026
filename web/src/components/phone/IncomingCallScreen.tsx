import { useState } from "react";

import type { PhoneMessage } from "../../api/types";
import { BeaconLogo } from "../ui/BeaconLogo";
import { Icon } from "../ui/icons";
import { ActiveCall } from "./ActiveCall";
import { useRingTone } from "./useRingTone";
import type { SpeechController } from "./useSpeech";

interface IncomingCallScreenProps {
  readonly message: PhoneMessage;
  readonly recipientName: string | null;
  readonly isAudioUnlocked: boolean;
  readonly initialAnswered?: boolean;
  readonly speech: SpeechController;
  readonly onAnsweredChange?: (answered: boolean) => void;
  /** Called when the call ends; `answered` tells whether it was picked up. */
  readonly onClose: (answered: boolean) => void;
}

/** Full-screen call overlay inside the phone: ringing screen, then active keypad call. */
export function IncomingCallScreen({
  message,
  recipientName,
  isAudioUnlocked,
  initialAnswered = false,
  speech,
  onAnsweredChange,
  onClose,
}: IncomingCallScreenProps) {
  const [isAnswered, setIsAnswered] = useState(initialAnswered);
  const { isMuted, toggleMute } = useRingTone(!isAnswered);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={
        isAnswered ? "Active call with Beacon alerts" : "Incoming call from Beacon alerts"
      }
      className="absolute inset-0 z-10 flex flex-col text-white"
    >
      {isAnswered ? (
        <ActiveCall
          message={message}
          recipientName={recipientName}
          speech={speech}
          autoSpeak={!initialAnswered}
          onHangUp={() => {
            onClose(true);
          }}
        />
      ) : (
        <div className="phone-call-backdrop flex h-full flex-col justify-between px-6 pt-3 pb-7">
          <div className="flex justify-end">
            <button
              type="button"
              aria-pressed={isMuted}
              aria-label={isMuted ? "Unmute ring tone" : "Mute ring tone"}
              onClick={toggleMute}
              className="inline-flex h-8 items-center gap-1.5 rounded-full bg-white/14 px-3 text-[12px] font-medium text-white/90 backdrop-blur-md transition-colors hover:bg-white/22"
            >
              <Icon name={isMuted ? "volumeOff" : "volume"} size={14} />
              {isMuted ? "Muted" : "Mute"}
            </button>
          </div>

          <div className="flex flex-col items-center text-center">
            <span className="mb-4 flex size-[72px] items-center justify-center rounded-full border border-white/20 bg-white/14 text-white backdrop-blur-md">
              <BeaconLogo size={32} aria-hidden="true" />
            </span>
            <p className="text-[26px] leading-[31px] font-semibold tracking-tight text-white">
              Beacon alerts
            </p>
            <p className="mt-1.5 text-[14px] text-white/75">Escalation needs your approval</p>
          </div>

          <div className="flex flex-col items-center gap-6">
            {!isAudioUnlocked ? (
              <p className="inline-flex items-center gap-1.5 rounded-full bg-white/14 px-3.5 py-1.5 text-[12px] font-medium text-white/85 backdrop-blur-md">
                <Icon name="volume" size={14} />
                Click anywhere to enable sound
              </p>
            ) : (
              <span className="h-7" aria-hidden="true" />
            )}

            <div className="flex w-full items-center justify-around">
              <div className="flex flex-col items-center gap-2">
                <button
                  type="button"
                  aria-label="Decline call"
                  onClick={() => {
                    onClose(false);
                  }}
                  className="flex size-16 items-center justify-center rounded-full bg-[#ff3b30] text-white shadow-lg transition-transform hover:bg-[#ff5147] active:scale-95"
                >
                  <Icon name="phoneOff" size={26} />
                </button>
                <span className="text-[13px] font-medium text-white/90">Decline</span>
              </div>

              <div className="flex flex-col items-center gap-2">
                <button
                  type="button"
                  aria-label="Accept call"
                  onClick={() => {
                    setIsAnswered(true);
                    onAnsweredChange?.(true);
                  }}
                  className="flex size-16 items-center justify-center rounded-full bg-[#34c759] text-white shadow-lg transition-transform hover:bg-[#46d369] active:scale-95"
                >
                  <Icon name="phone" size={26} />
                </button>
                <span className="text-[13px] font-medium text-white/90">Accept</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
