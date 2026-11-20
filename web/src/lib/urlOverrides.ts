import { applyTheme, isThemeValue, readStoredTheme, writeStoredTheme } from "./theme";
import { writeStoredTeamId } from "./teamStorage";

/**
 * Applies the stored theme and the demo/screenshot query params `?team=<id>` and
 * `?theme=light|dark|system` before the first render.
 */
export function applyUrlOverrides(): void {
  const params = new URLSearchParams(window.location.search);
  const team = params.get("team");
  if (team) {
    writeStoredTeamId(team);
  }
  const theme = params.get("theme");
  if (isThemeValue(theme)) {
    writeStoredTheme(theme);
  }
  applyTheme(readStoredTheme());
}
