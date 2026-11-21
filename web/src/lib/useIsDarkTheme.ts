import { useSyncExternalStore } from "react";

const QUERY = "(prefers-color-scheme: dark)";

function subscribe(onChange: () => void): () => void {
  const media = window.matchMedia(QUERY);
  media.addEventListener("change", onChange);
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  return () => {
    media.removeEventListener("change", onChange);
    observer.disconnect();
  };
}

function isDark(): boolean {
  const choice = document.documentElement.getAttribute("data-theme");
  return choice === "dark" || (choice !== "light" && window.matchMedia(QUERY).matches);
}

/** True while the app shows its dark appearance (explicit choice or system setting). */
export function useIsDarkTheme(): boolean {
  return useSyncExternalStore(subscribe, isDark);
}
