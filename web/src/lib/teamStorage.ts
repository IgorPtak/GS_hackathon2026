const TEAM_STORAGE_KEY = "alerting.team_id";

/**
 * Storage can be blocked (privacy modes, disabled cookies) and throw on access.
 * The UI must keep working without it, so every access is guarded.
 */
export function readStoredTeamId(): string | null {
  try {
    return window.localStorage.getItem(TEAM_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeStoredTeamId(teamId: string): void {
  try {
    window.localStorage.setItem(TEAM_STORAGE_KEY, teamId);
  } catch {
    // Not persisted: the selection still applies for this page view.
  }
}
