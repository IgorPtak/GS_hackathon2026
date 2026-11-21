export type TabId =
  | "home"
  | "inbox"
  | "approvals"
  | "phone"
  | "rules"
  | "connect"
  | "runbooks"
  | "people"
  | "insights"
  | "settings";

export interface TabDefinition {
  readonly id: TabId;
  /** UI label from docs/glossary.md. */
  readonly label: string;
  /** URL path of the page inside the shell. `/phone` itself is the full-screen route. */
  readonly path: string;
}

/** Rail order; `groupEnd` items are followed by a divider. */
export const TABS: readonly TabDefinition[] = [
  { id: "inbox", label: "Inbox", path: "/inbox" },
  { id: "approvals", label: "Approvals", path: "/approvals" },
  { id: "phone", label: "Phone", path: "/simulator" },
  { id: "rules", label: "Rules", path: "/rules" },
  { id: "connect", label: "Connect a system", path: "/connect" },
  { id: "runbooks", label: "Runbooks", path: "/runbooks" },
  { id: "people", label: "People & channels", path: "/people" },
  { id: "insights", label: "Insights", path: "/insights" },
];

/** Pages reached from the logo and the gear, not listed in the rail. */
export const EXTRA_PAGES: readonly TabDefinition[] = [
  { id: "home", label: "Home", path: "/home" },
  { id: "settings", label: "Settings", path: "/settings" },
];

export const ALL_PAGES: readonly TabDefinition[] = [...EXTRA_PAGES, ...TABS];

/** Tabs that start a new rail group, so a divider is drawn above them. */
export const GROUP_STARTS: readonly TabId[] = ["rules", "insights"];
