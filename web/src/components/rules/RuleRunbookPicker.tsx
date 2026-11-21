import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { RunbookSummary } from "../../api/types";
import { Select } from "../ui/Select";
import { readRunbookFromRuleYaml, writeRunbookToRuleYaml } from "./runbookYaml";

interface RuleRunbookPickerProps {
  readonly yaml: string;
  readonly ownerTeam: string;
  readonly onChange: (nextYaml: string) => void;
}

/** Which runbook an alert from this rule shows, picked from the team's (and shared) runbooks. */
export function RuleRunbookPicker({ yaml, ownerTeam, onChange }: RuleRunbookPickerProps) {
  const [runbooks, setRunbooks] = useState<readonly RunbookSummary[]>([]);
  useEffect(() => {
    let isCancelled = false;
    apiClient
      .GET("/api/v1/runbooks")
      .then(({ data }) => {
        if (!isCancelled && data) setRunbooks(data);
      })
      .catch(() => undefined);
    return () => {
      isCancelled = true;
    };
  }, []);

  const current = readRunbookFromRuleYaml(yaml);
  const mine = runbooks.filter((r) => r.team === ownerTeam || r.team === null);
  const options = [
    { value: "", label: "No runbook" },
    ...mine.map((r) => ({ value: r.id, label: r.title })),
    // Keep a runbook the list does not know (another team's, or not loaded yet) selectable.
    ...(current !== "" && !mine.some((r) => r.id === current)
      ? [{ value: current, label: current }]
      : []),
  ];
  return (
    <div className="space-y-2">
      <h4 className="text-body font-semibold">Runbook</h4>
      <p className="text-meta text-ink-2">
        What to do next. Its steps show on the alert, filled in with values from the event, and
        risky steps wait for approval. Add new ones under Runbooks.
      </p>
      <Select
        aria-label="Runbook"
        options={options}
        value={current}
        onChange={(id) => {
          onChange(writeRunbookToRuleYaml(yaml, id));
        }}
      />
    </div>
  );
}
