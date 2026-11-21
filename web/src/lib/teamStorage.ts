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

const PERSON_STORAGE_KEY = "alerting.person_id";

/** Who signed in (a recipient id). There is no real authentication: this only picks a view. */
export function readStoredPersonId(): string | null {
  try {
    return window.localStorage.getItem(PERSON_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function writeStoredPersonId(personId: string | null): void {
  try {
    if (personId === null) {
      window.localStorage.removeItem(PERSON_STORAGE_KEY);
      window.localStorage.removeItem(TEAM_STORAGE_KEY);
    } else {
      window.localStorage.setItem(PERSON_STORAGE_KEY, personId);
    }
  } catch {
    // Not persisted: the choice still applies for this page view.
  }
}
