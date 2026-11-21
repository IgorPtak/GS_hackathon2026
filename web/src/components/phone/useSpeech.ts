import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { playSpeechChime } from "./playChime";
import {
  pickBestVoice,
  readStoredVoiceUri,
  sortVoicesForPicker,
  subscribeVoiceChoice,
  writeStoredVoiceUri,
} from "./voiceSelection";

function readVoices(): readonly SpeechSynthesisVoice[] {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return [];
  try {
    return window.speechSynthesis.getVoices();
  } catch {
    return [];
  }
}

export interface SpeechController {
  readonly isSupported: boolean;
  readonly voices: readonly SpeechSynthesisVoice[];
  readonly selectedVoiceUri: string;
  readonly activeVoice: SpeechSynthesisVoice | null;
  readonly setSelectedVoiceUri: (uri: string) => void;
  readonly speakSentences: (
    sentences: readonly string[],
    options?: { readonly withChime?: boolean },
  ) => void;
  readonly cancel: () => void;
}

/**
 * Browser speech synthesis with best-voice selection, `voiceschanged` support,
 * persisted voice choice, a pleasant chime, and queued short utterances.
 */
export function useSpeech(): SpeechController {
  const isSupported = typeof window !== "undefined" && "speechSynthesis" in window;
  const [rawVoices, setRawVoices] = useState<readonly SpeechSynthesisVoice[]>(readVoices);
  const selectedVoiceUri = useSyncExternalStore(subscribeVoiceChoice, readStoredVoiceUri);
  // Keep references to queued utterances so the browser does not garbage-collect them mid-speech.
  const utterancesRef = useRef<SpeechSynthesisUtterance[]>([]);
  const generationRef = useRef(0);

  useEffect(() => {
    if (!isSupported) return;
    const synth = window.speechSynthesis;
    const refresh = () => {
      setRawVoices(readVoices());
    };
    refresh();
    synth.addEventListener("voiceschanged", refresh);
    return () => {
      synth.removeEventListener("voiceschanged", refresh);
    };
  }, [isSupported]);

  const voices = useMemo(() => sortVoicesForPicker(rawVoices), [rawVoices]);

  const activeVoice = useMemo(() => {
    if (selectedVoiceUri !== "") {
      const explicit = voices.find((voice) => voice.voiceURI === selectedVoiceUri);
      if (explicit) return explicit;
    }
    return pickBestVoice(rawVoices);
  }, [rawVoices, voices, selectedVoiceUri]);

  const setSelectedVoiceUri = useCallback((uri: string) => {
    writeStoredVoiceUri(uri);
  }, []);

  const cancel = useCallback(() => {
    generationRef.current += 1;
    utterancesRef.current = [];
    if (!isSupported) return;
    try {
      window.speechSynthesis.cancel();
    } catch {
      // Speech is best effort.
    }
  }, [isSupported]);

  const speakSentences = useCallback(
    (sentences: readonly string[], options?: { readonly withChime?: boolean }) => {
      if (!isSupported || sentences.length === 0) return;
      const runId = generationRef.current + 1;
      generationRef.current = runId;

      try {
        window.speechSynthesis.cancel();
      } catch {
        // Ignore cancel errors.
      }

      const startSpeaking = () => {
        if (generationRef.current !== runId) return;
        const queued: SpeechSynthesisUtterance[] = [];
        for (const sentence of sentences) {
          const utterance = new SpeechSynthesisUtterance(sentence);
          if (activeVoice) {
            utterance.voice = activeVoice;
            utterance.lang = activeVoice.lang;
          } else {
            utterance.lang = "en-US";
          }
          utterance.rate = 0.95;
          utterance.pitch = 1.0;
          queued.push(utterance);
        }
        utterancesRef.current = queued;
        try {
          for (const utterance of queued) {
            window.speechSynthesis.speak(utterance);
          }
        } catch {
          // Speech is best effort.
        }
      };

      if (options?.withChime === false) {
        startSpeaking();
      } else {
        void playSpeechChime().then(startSpeaking);
      }
    },
    [activeVoice, isSupported],
  );

  useEffect(() => cancel, [cancel]);

  return {
    isSupported,
    voices,
    selectedVoiceUri,
    activeVoice,
    setSelectedVoiceUri,
    speakSentences,
    cancel,
  };
}
