export type TabId = "alerts" | "rules" | "runbooks" | "approvals" | "schemas" | "phone" | "metrics";

export interface TabDefinition {
  readonly id: TabId;
  readonly label: string;
}

/** Tab order and labels follow the plan; each tab gets its own page in later tasks. */
export const TABS: readonly TabDefinition[] = [
  { id: "alerts", label: "Alerts" },
  { id: "rules", label: "Rules" },
  { id: "runbooks", label: "Runbooks" },
  { id: "approvals", label: "Approvals" },
  { id: "schemas", label: "Schemas" },
  { id: "phone", label: "Phone" },
  { id: "metrics", label: "Metrics" },
];
