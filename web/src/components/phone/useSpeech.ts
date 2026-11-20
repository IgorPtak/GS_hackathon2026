import { useCallback, useEffect, useRef } from "react";

/** Browser speech synthesis; `isSupported` is false when the API is missing. */
export function useSpeech() {
  const isSupported = typeof window !== "undefined" && "speechSynthesis" in window;
  // Keep a reference so the utterance is not garbage collected mid-speech.
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  const cancel = useCallback(() => {
    if (!isSupported) return;
    try {
      window.speechSynthesis.cancel();
    } catch {
      // Speech is best effort.
    }
  }, [isSupported]);

  const speak = useCallback(
    (text: string) => {
      if (!isSupported) return;
      try {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "en-US";
        utterance.rate = 0.95;
        utteranceRef.current = utterance;
        window.speechSynthesis.speak(utterance);
      } catch {
        // Speech is best effort.
      }
    },
    [isSupported],
  );

  useEffect(() => cancel, [cancel]);

  return { isSupported, speak, cancel };
}
