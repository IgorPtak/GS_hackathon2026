import type { ConfigValidationError } from "../../api/types";
import { FieldErrors } from "./FieldErrors";
import { existsPaths, matchFromPaths, type Match } from "./schemaDraft";

interface MatchConditionsEditorProps {
  readonly match: Match;
  readonly paths: readonly string[];
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (match: Match) => void;
}

/** Match conditions: every listed key path must exist in the event. */
export function MatchConditionsEditor({
  match,
  paths,
  errors,
  onChange,
}: MatchConditionsEditorProps) {
  const selected = existsPaths(match);
  return (
    <fieldset className="space-y-1">
      <legend className="text-sm font-medium">Match conditions (all key paths must exist)</legend>
      {selected === null ? (
        <p className="text-xs text-slate-600">
          This profile uses a custom match condition; it is kept as proposed.
        </p>
      ) : (
        <>
          {selected.map((path, index) => (
            <div key={index} className="flex items-center gap-2">
              <select
                aria-label={`Match key path ${String(index + 1)}`}
                value={path}
                onChange={(e) => {
                  onChange(
                    matchFromPaths(selected.map((p, i) => (i === index ? e.target.value : p))),
                  );
                }}
                className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 font-mono text-sm"
              >
                {[...new Set([path, ...paths])].map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              <span className="text-xs text-slate-500">exists</span>
              <button
                type="button"
                aria-label={`Remove match condition ${path}`}
                disabled={selected.length <= 1}
                onClick={() => {
                  onChange(matchFromPaths(selected.filter((_, i) => i !== index)));
                }}
                className="px-1 text-slate-500 disabled:opacity-30"
              >
                x
              </button>
            </div>
          ))}
          <button
            type="button"
            disabled={paths.length === 0}
            onClick={() => {
              const next = paths.find((p) => !selected.includes(p)) ?? paths[0];
              if (next !== undefined) onChange(matchFromPaths([...selected, next]));
            }}
            className="rounded border border-slate-300 bg-white px-2 py-0.5 text-sm disabled:opacity-40"
          >
            Add condition
          </button>
        </>
      )}
      <FieldErrors errors={errors} />
    </fieldset>
  );
}
