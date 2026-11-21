const VOICE_STORAGE_KEY = "beacon-phone-voice";

const PREFERRED_REGIONS = ["en-us", "en-gb"] as const;
const PREMIUM_MARKERS = ["premium", "siri", "enhanced"] as const;
const NAMED_FAVORITES = ["samantha", "ava", "zoe", "daniel"] as const;

/**
 * macOS novelty and robotic "Eloquence" voices: English-tagged, but they sing, whisper or sound
 * like a 1980s computer. Never offered, never picked.
 */
const NOVELTY_VOICES = new Set([
  "albert",
  "bad news",
  "bahh",
  "bells",
  "boing",
  "bubbles",
  "cellos",
  "good news",
  "jester",
  "organ",
  "superstar",
  "trinoids",
  "whisper",
  "wobble",
  "zarvox",
  "junior",
  "ralph",
  "fred",
  "kathy",
  "grandma",
  "grandpa",
  "rocko",
  "shelley",
  "eddy",
  "flo",
  "reed",
  "sandy",
]);

function isNovelty(voice: SpeechSynthesisVoice): boolean {
  const base = voice.name
    .toLowerCase()
    .replace(/\s*\(.*\)\s*$/, "")
    .trim();
  return NOVELTY_VOICES.has(base);
}

const REGION_NAMES: Record<string, string> = {
  "en-us": "US English",
  "en-gb": "British English",
  "en-au": "Australian English",
  "en-ie": "Irish English",
  "en-in": "Indian English",
  "en-za": "South African English",
  "en-ca": "Canadian English",
  "en-nz": "New Zealand English",
};

function normalizeLang(lang: string): string {
  return lang.toLowerCase().replace("_", "-");
}

function isPreferredEnglish(lang: string): boolean {
  const norm = normalizeLang(lang);
  return PREFERRED_REGIONS.some((region) => norm === region || norm.startsWith(`${region}-`));
}

function isAnyEnglish(lang: string): boolean {
  const norm = normalizeLang(lang);
  return norm === "en" || norm.startsWith("en-");
}

/** Higher score = better voice for spoken escalation calls. */
function scoreVoice(voice: SpeechSynthesisVoice): number {
  const name = voice.name.toLowerCase();
  const preferred = isPreferredEnglish(voice.lang);
  const english = isAnyEnglish(voice.lang);

  if (preferred) {
    const markerIndex = PREMIUM_MARKERS.findIndex((marker) => name.includes(marker));
    if (markerIndex !== -1) {
      const favoriteBoost = NAMED_FAVORITES.some((fav) => name.includes(fav)) ? 10 : 0;
      const localBoost = voice.localService ? 5 : 0;
      return 400 - markerIndex * 20 + favoriteBoost + localBoost;
    }
  }

  if (english) {
    const favIndex = NAMED_FAVORITES.findIndex((fav) => name.includes(fav));
    if (favIndex !== -1) {
      return 300 - favIndex * 15 + (preferred ? 8 : 0) + (voice.localService ? 4 : 0);
    }
    if (voice.localService) {
      return preferred ? 220 : 200;
    }
    return preferred ? 120 : 100;
  }

  return voice.default ? 10 : 0;
}

/** Picks the best installed English voice for Beacon calls. */
export function pickBestVoice(
  voices: readonly SpeechSynthesisVoice[],
): SpeechSynthesisVoice | null {
  let best: SpeechSynthesisVoice | null = null;
  let bestScore = -1;
  for (const candidate of voices) {
    if (isNovelty(candidate)) continue;
    const score = scoreVoice(candidate);
    if (best === null || score > bestScore) {
      best = candidate;
      bestScore = score;
    }
  }
  return best;
}

/** English voices only (Beacon speaks English), novelty voices out, best at the top. */
export function sortVoicesForPicker(
  voices: readonly SpeechSynthesisVoice[],
): readonly SpeechSynthesisVoice[] {
  const english = voices.filter((voice) => isAnyEnglish(voice.lang) && !isNovelty(voice));
  const pool = english.length > 0 ? english : voices;
  return [...pool].sort((a, b) => scoreVoice(b) - scoreVoice(a) || a.name.localeCompare(b.name));
}

/** Human-readable label for a voice option. */
export function formatVoiceLabel(voice: SpeechSynthesisVoice): string {
  const region = REGION_NAMES[normalizeLang(voice.lang)] ?? voice.lang.replace("_", "-");
  const name = voice.name.replace(/^(Microsoft|Google)\s+/, "").replace(/\s*-\s*English.*$/, "");
  return `${name} · ${region}`;
}

/* The chosen voice is shared by every phone and the Settings picker in this tab. */
const voiceListeners = new Set<() => void>();

export function subscribeVoiceChoice(listener: () => void): () => void {
  voiceListeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === VOICE_STORAGE_KEY) listener();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    voiceListeners.delete(listener);
    window.removeEventListener("storage", onStorage);
  };
}

export function readStoredVoiceUri(): string {
  try {
    return window.localStorage.getItem(VOICE_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function writeStoredVoiceUri(uri: string): void {
  try {
    if (uri === "") {
      window.localStorage.removeItem(VOICE_STORAGE_KEY);
    } else {
      window.localStorage.setItem(VOICE_STORAGE_KEY, uri);
    }
  } catch {
    // Preference simply will not persist in restricted storage modes.
  }
  voiceListeners.forEach((listener) => {
    listener();
  });
}
