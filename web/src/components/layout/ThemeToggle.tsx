import { nextTheme, type ThemePreference } from "../../lib/theme";
import { Icon, type IconName } from "../ui/icons";
import { Tooltip } from "../ui/Tooltip";

const ICONS: Record<ThemePreference, IconName> = { system: "auto", light: "sun", dark: "moon" };
const WORDS: Record<ThemePreference, string> = { system: "System", light: "Light", dark: "Dark" };

/** Cycles system, light, dark. The label names the current choice and what a click does. */
export function ThemeToggle({ theme, onCycle }: { theme: ThemePreference; onCycle: () => void }) {
  return (
    <Tooltip label={`Appearance: ${WORDS[theme]}`}>
      <button
        type="button"
        onClick={onCycle}
        aria-label={`Appearance: ${WORDS[theme]}. Switch to ${WORDS[nextTheme(theme)]}`}
        className="flex size-11 items-center justify-center rounded-tile text-ink-2 hover:bg-fill hover:text-ink"
      >
        <Icon name={ICONS[theme]} size={22} />
      </button>
    </Tooltip>
  );
}
