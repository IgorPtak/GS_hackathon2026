/** Team colours are used for avatars and monograms only (docs/ui-design.md "Team colours"). */
const TEAM_COLORS: Record<string, string> = {
  rates: "var(--team-rates)",
  settlements: "var(--team-settlements)",
  pricing: "var(--team-pricing)",
  platform: "var(--team-platform)",
};

/** The API has no team description field, so the one-line blurbs live here. */
const TEAM_BLURBS: Record<string, string> = {
  rates: "Rate trades, large rejections and curve feeds.",
  settlements: "Settlement workflows, confirmations and breaks.",
  pricing: "Pricing engines, quotes and market data.",
  platform: "Infrastructure, gateways and the pipeline itself.",
};

export function teamColor(teamId: string | null | undefined): string {
  return (teamId ? TEAM_COLORS[teamId] : undefined) ?? "var(--ink-2)";
}

export function teamBlurb(teamId: string): string {
  return TEAM_BLURBS[teamId] ?? "Alerts and runbooks for this team.";
}

/** "Team Rates" becomes "Rates"; the glossary UI label is the bare team name. */
export function teamShortName(displayName: string): string {
  return displayName.replace(/^Team\s+/i, "");
}
