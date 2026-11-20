import { useCallback, useState } from "react";

import {
  applyTheme,
  nextTheme,
  readStoredTheme,
  writeStoredTheme,
  type ThemePreference,
} from "./theme";

/** Appearance preference: system, light or dark; persisted and mirrored on <html data-theme>. */
export function useTheme(): { theme: ThemePreference; cycleTheme: () => void } {
  const [theme, setTheme] = useState<ThemePreference>(() => readStoredTheme());

  const cycleTheme = useCallback(() => {
    const next = nextTheme(theme);
    applyTheme(next);
    writeStoredTheme(next);
    setTheme(next);
  }, [theme]);

  return { theme, cycleTheme };
}
