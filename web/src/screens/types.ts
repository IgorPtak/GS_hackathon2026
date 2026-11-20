import type { TabId } from "../lib/tabs";

/** What the shell hands every screen. */
export interface ScreenProps {
  readonly teamId: string;
  /** Display name of the team, e.g. "Rates". */
  readonly teamLabel: string;
  readonly onNavigate: (tab: TabId) => void;
}
