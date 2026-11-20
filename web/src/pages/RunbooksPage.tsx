import { useState } from "react";

import { RunbookDetailView } from "../components/runbooks/RunbookDetailView";
import { useRunbooks } from "../components/runbooks/useRunbooks";

/** Runbooks tab: list of stored runbooks; selecting one shows its source next to its steps. */
export function RunbooksPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const state = useRunbooks(selectedId);

  return (
    <section aria-labelledby="runbooks-title">
      <h2 id="runbooks-title" className="mb-3 text-xl font-semibold">
        Runbooks
      </h2>
      {state.isListLoading ? <p className="text-sm text-slate-500">Loading runbooks...</p> : null}
      {state.listError ? (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          Cannot load runbooks ({state.listError}).
        </p>
      ) : null}
      {!state.isListLoading && !state.listError && state.summaries.length === 0 ? (
        <p className="text-sm text-slate-500">No runbooks yet</p>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-[18rem_1fr]">
        <ul className="space-y-1">
          {state.summaries.map((item) => (
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
                <span className="block font-medium break-words">{item.title}</span>
                <span className="block text-xs text-slate-500">
                  {item.format} · {item.step_count} steps · {item.normalized_by}
                  {item.llm_model ? ` (${item.llm_model})` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
        <div className="min-w-0">
          {selectedId === null && state.summaries.length > 0 ? (
            <p className="text-sm text-slate-500">Select a runbook to see its source and steps.</p>
          ) : null}
          {state.isRunbookLoading ? (
            <p className="text-sm text-slate-500">Loading runbook...</p>
          ) : null}
          {state.runbookError ? (
            <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
              Cannot load runbook ({state.runbookError}).
            </p>
          ) : null}
          {state.runbook ? <RunbookDetailView runbook={state.runbook} /> : null}
        </div>
      </div>
    </section>
  );
}
