import { useEffect, useState } from "react";

let audioUnlocked = false;

/**
 * Tracks whether the user has interacted with the page so the browser allows WebAudio and speech.
 * Shows a one-time hint until the first click, tap, or key press.
 */
export function useAudioUnlock(): boolean {
  const [isUnlocked, setIsUnlocked] = useState(audioUnlocked);

  useEffect(() => {
    if (audioUnlocked) return;

    function unlock() {
      audioUnlocked = true;
      setIsUnlocked(true);
      try {
        const Ctor: typeof AudioContext | undefined = window.AudioContext;
        if (typeof Ctor === "function") {
          const ctx = new Ctor();
          void ctx.resume().finally(() => {
            void ctx.close().catch(() => undefined);
          });
        }
      } catch {
        // Best effort unlock.
      }
      window.removeEventListener("pointerdown", unlock, true);
      window.removeEventListener("keydown", unlock, true);
    }

    window.addEventListener("pointerdown", unlock, true);
    window.addEventListener("keydown", unlock, true);
    return () => {
      window.removeEventListener("pointerdown", unlock, true);
      window.removeEventListener("keydown", unlock, true);
    };
  }, []);

  return isUnlocked;
}
