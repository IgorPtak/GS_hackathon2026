import { useSyncExternalStore } from "react";

/**
 * First-run state kept in this browser: has this person seen the welcome, and has a team hidden its
 * setup checklist. Storage can throw (privacy modes), so every access is guarded and the UI
 * falls back to showing the guide.
 */
const WELCOME_KEY_PREFIX = "beacon.welcome_seen.";
const CHECKLIST_KEY_PREFIX = "beacon.setup_hidden.";
const CHANGE_EVENT = "beacon:onboarding-changed";

function read(key: string): boolean {
  try {
    return window.localStorage.getItem(key) === "1";
  } catch {
    return false;
  }
}

function write(key: string, value: boolean): void {
  try {
    if (value) window.localStorage.setItem(key, "1");
    else window.localStorage.removeItem(key);
  } catch {
    // Not persisted: the choice still applies until the page reloads.
  }
  window.dispatchEvent(new Event(CHANGE_EVENT));
}

function subscribe(listener: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(CHANGE_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}

/** Per person, so each teammate who signs in on this browser gets the welcome once. */
export function useHasSeenWelcome(personId: string): boolean {
  return useSyncExternalStore(subscribe, () => read(WELCOME_KEY_PREFIX + personId));
}

export function markWelcomeSeen(personId: string, isSeen = true): void {
  write(WELCOME_KEY_PREFIX + personId, isSeen);
}

export function useIsChecklistHidden(teamId: string): boolean {
  return useSyncExternalStore(subscribe, () => read(CHECKLIST_KEY_PREFIX + teamId));
}

export function setChecklistHidden(teamId: string, isHidden: boolean): void {
  write(CHECKLIST_KEY_PREFIX + teamId, isHidden);
}
