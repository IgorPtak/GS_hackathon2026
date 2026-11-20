import { useState } from "react";

import type { UnknownSchemaSample } from "../../api/types";
import { parseSampleJson, type SampleEvent } from "./schemaDraft";

interface UnknownSchemaInboxProps {
  readonly samples: readonly UnknownSchemaSample[];
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly onPick: (sample: SampleEvent, label: string) => void;
}

const PREVIEW_PATHS = 6;

function PasteJsonForm({ onPick }: { readonly onPick: UnknownSchemaInboxProps["onPick"] }) {
  const [text, setText] = useState("");
  const parsed = text.trim() === "" ? null : parseSampleJson(text);
  const parseError = parsed && "error" in parsed ? parsed.error : null;

  return (
    <div className="space-y-2">
      <label htmlFor="paste-json" className="block text-sm font-medium">
        Paste a sample JSON event
      </label>
      <textarea
        id="paste-json"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
        }}
        rows={6}
        spellCheck={false}
        className="w-full rounded border border-slate-300 bg-white p-2 font-mono text-xs"
        placeholder='{"evt": "payment.declined", "lvl": "WARN", ...}'
      />
      {parseError ? (
        <p role="alert" className="text-sm text-red-700">
          Invalid JSON: {parseError}
        </p>
      ) : null}
      <button
        type="button"
        disabled={!parsed || "error" in parsed}
        onClick={() => {
          if (parsed && "sample" in parsed) onPick(parsed.sample, "pasted JSON");
        }}
        className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-40"
      >
        Propose a schema
      </button>
    </div>
  );
}

/** Unknown-schema inbox (cards per distinct key shape) plus the paste-JSON alternative. */
export function UnknownSchemaInbox({ samples, isLoading, error, onPick }: UnknownSchemaInboxProps) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="mb-2 text-lg font-semibold">Unknown schema inbox</h3>
        {isLoading ? <p className="text-sm text-slate-500">Loading unknown schemas...</p> : null}
        {error ? (
          <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
            Cannot load unknown schemas ({error}).
          </p>
        ) : null}
        {!isLoading && !error && samples.length === 0 ? (
          <p className="text-sm text-slate-500">
            No unknown schemas. Events that match no profile will appear here.
          </p>
        ) : null}
        <ul className="grid gap-2 md:grid-cols-2">
          {samples.map((s) => (
            <li key={s.shape_hash} className="rounded border border-slate-200 bg-white p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium break-all">{s.source_id}</span>
                <span className="text-xs text-slate-600">{s.event_count} events</span>
              </div>
              <p className="text-xs text-slate-500">
                First seen {new Date(s.first_seen).toLocaleString()} · last seen{" "}
                {new Date(s.last_seen).toLocaleString()}
              </p>
              <p className="my-2 font-mono text-xs break-all text-slate-700">
                {s.key_paths.slice(0, PREVIEW_PATHS).join(", ")}
                {s.key_paths.length > PREVIEW_PATHS
                  ? ` +${String(s.key_paths.length - PREVIEW_PATHS)} more`
                  : ""}
              </p>
              <button
                type="button"
                onClick={() => {
                  onPick(s.sample_event, s.source_id);
                }}
                className="rounded bg-slate-800 px-3 py-1 text-sm text-white"
              >
                Propose a schema
              </button>
            </li>
          ))}
        </ul>
      </div>
      <PasteJsonForm onPick={onPick} />
    </div>
  );
}
