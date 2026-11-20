const VOICE_STORAGE_KEY = "beacon-phone-voice";

const PREFERRED_REGIONS = ["en-us", "en-gb"] as const;
const PREMIUM_MARKERS = ["premium", "siri", "enhanced"] as const;
const NAMED_FAVORITES = ["samantha", "ava", "zoe", "daniel"] as const;

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
    const score = scoreVoice(candidate);
    if (best === null || score > bestScore) {
      best = candidate;
      bestScore = score;
    }
  }
  return best;
}

/** Filters and sorts voices for the presenter's picker: English voices first, best at top. */
export function sortVoicesForPicker(
  voices: readonly SpeechSynthesisVoice[],
): readonly SpeechSynthesisVoice[] {
  const english = voices.filter((voice) => isAnyEnglish(voice.lang));
  const pool = english.length > 0 ? english : voices;
  return [...pool].sort((a, b) => scoreVoice(b) - scoreVoice(a) || a.name.localeCompare(b.name));
}

/** Human-readable label for a voice option. */
export function formatVoiceLabel(voice: SpeechSynthesisVoice): string {
  const lang = voice.lang.replace("_", "-");
  return `${voice.name} (${lang})`;
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
}
