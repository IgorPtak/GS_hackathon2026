import { useState } from "react";

import type { RuleRecord } from "../api/types";
import { RecipientsSection } from "../components/recipients/RecipientsSection";
import { RuleEditor } from "../components/rules/RuleEditor";
import { useRules } from "../components/rules/useRules";

function RulesView({ team }: { readonly team: string }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saved, setSaved] = useState<RuleRecord | null>(null);
  const state = useRules(team);
  const listed = state.rules.find((r) => r.id === selectedId) ?? null;
  const record =
    saved?.id === selectedId && saved.version >= (listed?.version ?? 0) ? saved : listed;

  return (
    <div className="space-y-3">
      {state.isLoading ? <p className="text-sm text-slate-500">Loading rules...</p> : null}
      {state.error ? (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          Cannot load rules ({state.error}).
        </p>
      ) : null}
      {!state.isLoading && !state.error && state.rules.length === 0 ? (
        <p className="text-sm text-slate-500">No rules for this team yet</p>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
        <ul className="space-y-1">
          {state.rules.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                aria-pressed={item.id === selectedId}
                onClick={() => {
                  setSelectedId(item.id);
                }}
                className={`w-full rounded border px-3 py-2 text-left text-sm ${
                  item.id === selectedId
                    ? "border-slate-800 bg-white"
                    : "border-slate-200 bg-white hover:bg-slate-50"
                }`}
              >
                <span className="block font-medium break-words">{item.rule.present.title}</span>
                <span className="block text-xs break-all text-slate-500">{item.id}</span>
                <span className="block text-xs text-slate-500">
                  v{item.version} · {new Date(item.updated_at).toLocaleString()}
                  {item.updated_by ? ` · ${item.updated_by.id}` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="min-w-0">
          {record ? (
            <RuleEditor
              key={`${record.id}@${String(record.version)}`}
              record={record}
              team={team}
              onSaved={(next) => {
                setSaved(next);
                state.reload();
              }}
            />
          ) : (
            <p className="text-sm text-slate-500">Select a rule to edit its YAML.</p>
          )}
        </div>
      </div>
    </div>
  );
}

/** Rules tab: pick a rule of the team, edit it as YAML, preview and save a new version. */
export function RulesPage({ teamId }: { readonly teamId: string | null }) {
  return (
    <section aria-labelledby="rules-title">
      <h2 id="rules-title" className="mb-3 text-xl font-semibold">
        Rules
      </h2>
      {teamId === null ? (
        <p className="text-sm text-slate-500">Pick a team to see its rules.</p>
      ) : (
        <RulesView key={teamId} team={teamId} />
      )}
      {teamId === null ? null : <RecipientsSection key={`recipients-${teamId}`} team={teamId} />}
    </section>
  );
}
