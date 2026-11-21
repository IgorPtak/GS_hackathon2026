import { useState } from "react";

import type { RuleRecord } from "../api/types";
import { RuleEditor } from "../components/rules/RuleEditor";
import { RuleListCard } from "../components/rules/RuleListCard";
import { newRuleYaml } from "../components/rules/topLevelYaml";
import { useRules } from "../components/rules/useRules";
import { EmptyState } from "../components/ui/EmptyState";
import { Pill } from "../components/ui/Pill";
import { Skeleton } from "../components/ui/Skeleton";
import { useToast } from "../components/ui/toastContext";

/** `null` is the list, "new" a rule that does not exist yet, anything else a rule id. */
export type RulesSelection = string | null;
export const NEW_RULE = "new";

type Filter = "all" | "enabled" | "disabled";

interface RulesPageProps {
  readonly teamId: string;
  readonly selection: RulesSelection;
  readonly onSelect: (selection: RulesSelection) => void;
}

function RulesList({
  rules,
  onSelect,
}: {
  readonly rules: readonly RuleRecord[];
  readonly onSelect: (id: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const enabled = rules.filter((r) => r.rule.enabled).length;
  const shown = rules.filter((r) => filter === "all" || (filter === "enabled") === r.rule.enabled);
  return (
    <div className="space-y-4">
      <div role="toolbar" aria-label="Filter rules" className="flex flex-wrap gap-2">
        <Pill
          isActive={filter === "all"}
          count={rules.length}
          onToggle={() => {
            setFilter("all");
          }}
        >
          All
        </Pill>
        <Pill
          isActive={filter === "enabled"}
          count={enabled}
          onToggle={() => {
            setFilter("enabled");
          }}
        >
          Enabled
        </Pill>
        <Pill
          isActive={filter === "disabled"}
          count={rules.length - enabled}
          onToggle={() => {
            setFilter("disabled");
          }}
        >
          Disabled
        </Pill>
      </div>
      <ul className="space-y-3">
        {shown.map((record) => (
          <RuleListCard
            key={record.id}
            record={record}
            onOpen={() => {
              onSelect(record.id);
            }}
          />
        ))}
      </ul>
    </div>
  );
}

/** The team's rules as cards, or the 3-step flow for the opened or new rule. */
export function RulesPage({ teamId, selection, onSelect }: RulesPageProps) {
  const [saved, setSaved] = useState<RuleRecord | null>(null);
  const state = useRules(teamId);
  const toast = useToast();
  const listed = state.rules.find((r) => r.id === selection) ?? null;
  const record =
    saved?.id === selection && saved.version >= (listed?.version ?? 0) ? saved : listed;

  function handleSaved(next: RuleRecord) {
    setSaved(next);
    state.reload();
    toast.show(`Saved ${next.id}`);
    if (selection === NEW_RULE) onSelect(next.id);
  }

  if (selection === NEW_RULE) {
    return (
      <RuleEditor
        key="new"
        source={{ id: null, yaml: newRuleYaml(teamId) }}
        version={null}
        team={teamId}
        onSaved={handleSaved}
      />
    );
  }
  if (selection !== null && record) {
    return (
      <RuleEditor
        key={record.id}
        source={{ id: record.id, yaml: record.yaml }}
        version={record.version}
        team={teamId}
        onSaved={handleSaved}
      />
    );
  }
  if (state.isLoading) return <Skeleton className="h-40 w-full" />;
  if (state.error) {
    return (
      <p role="alert" className="rounded-tile bg-critical/12 px-4 py-3 text-critical-ink">
        Cannot load rules ({state.error}). Check that the API is running, then reload.
      </p>
    );
  }
  if (state.rules.length === 0) {
    return (
      <EmptyState
        icon="rules"
        action={
          <button
            type="button"
            onClick={() => {
              onSelect(NEW_RULE);
            }}
            className="h-9 rounded-full bg-ink px-4 text-body font-medium text-window"
          >
            New rule
          </button>
        }
      >
        This team has no rules yet. Create one to turn events into alerts.
      </EmptyState>
    );
  }
  return <RulesList rules={state.rules} onSelect={onSelect} />;
}
