import { useEffect, useState } from "react";

const MUTE_KEY = "phone-ring-muted";

function readMuted(): boolean {
  try {
    return window.localStorage.getItem(MUTE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Soft two-tone ring generated with Web Audio while `isRinging`; mute is persisted. */
export function useRingTone(isRinging: boolean) {
  const [isMuted, setIsMuted] = useState(readMuted);

  useEffect(() => {
    if (!isRinging || isMuted) return;
    const Ctor: typeof AudioContext | undefined = window.AudioContext;
    if (typeof Ctor !== "function") return;
    let ctx: AudioContext;
    try {
      ctx = new Ctor();
    } catch {
      return;
    }
    const audio = ctx;
    function ring() {
      void audio.resume().catch(() => undefined);
      [440, 520].forEach((freq, i) => {
        const start = audio.currentTime + i * 0.3;
        const osc = audio.createOscillator();
        const gain = audio.createGain();
        osc.frequency.value = freq;
        gain.gain.setValueAtTime(0, start);
        gain.gain.linearRampToValueAtTime(0.06, start + 0.03);
        gain.gain.linearRampToValueAtTime(0, start + 0.25);
        osc.connect(gain).connect(audio.destination);
        osc.start(start);
        osc.stop(start + 0.27);
      });
    }
    ring();
    const timer = window.setInterval(ring, 2000);
    return () => {
      window.clearInterval(timer);
      void audio.close().catch(() => undefined);
    };
  }, [isRinging, isMuted]);

  function toggleMute() {
    const next = !isMuted;
    setIsMuted(next);
    try {
      window.localStorage.setItem(MUTE_KEY, next ? "1" : "0");
    } catch {
      // Preference just will not persist.
    }
  }

  return { isMuted, toggleMute };
}
