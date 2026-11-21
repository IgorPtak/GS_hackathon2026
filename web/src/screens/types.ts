import type { Recipient, Team } from "../api/types";
import type { TabId } from "../lib/tabs";

/** What the shell hands every screen. */
export interface ScreenProps {
  readonly teamId: string;
  /** Display name of the team, e.g. "Rates". */
  readonly teamLabel: string;
  /** Jump to another page from inside this one; the header then offers a way back. */
  readonly onNavigate: (tab: TabId) => void;
  /** The signed-in person, when known. */
  readonly person: Recipient | null;
  readonly teams: readonly Team[];
  readonly onSelectTeam: (teamId: string) => void;
  readonly onSignOut: () => void;
}
