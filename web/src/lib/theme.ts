export type ThemePreference = "system" | "light" | "dark";

const THEME_STORAGE_KEY = "alerting.theme";
const ORDER: readonly ThemePreference[] = ["system", "light", "dark"];

function isThemePreference(value: unknown): value is ThemePreference {
  return value === "system" || value === "light" || value === "dark";
}

export function readStoredTheme(): ThemePreference {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return isThemePreference(value) ? value : "system";
  } catch {
    return "system";
  }
}

/** Sets or clears <html data-theme>; "system" removes it so the OS preference applies. */
export function applyTheme(theme: ThemePreference): void {
  if (theme === "system") {
    document.documentElement.removeAttribute("data-theme");
  } else {
    document.documentElement.setAttribute("data-theme", theme);
  }
}

export function writeStoredTheme(theme: ThemePreference): void {
  try {
    if (theme === "system") {
      window.localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    }
  } catch {
    // Not persisted: the choice still applies for this page view.
  }
}

export function nextTheme(theme: ThemePreference): ThemePreference {
  return ORDER[(ORDER.indexOf(theme) + 1) % ORDER.length] ?? "system";
}

export function isThemeValue(value: string | null): value is ThemePreference {
  return isThemePreference(value);
}
