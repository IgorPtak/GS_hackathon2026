import { useState } from "react";

import { apiClient } from "../../api/client";
import type { Rule, RulePreview } from "../../api/types";
import { RulePreviewResult } from "./RulePreviewResult";
import { messageFromBody } from "./ruleErrors";

const WINDOWS = ["15m", "1h", "6h", "24h"] as const;

interface Run {
  readonly yaml: string;
  readonly window: string;
  readonly preview: RulePreview;
}

function failureText(status: number, body: unknown): string {
  if (status === 404 || status === 503) return "Preview is not available yet on this server.";
  return messageFromBody(body, `Preview failed (API error ${String(status)})`);
}

/** Runs the draft rule over the last window of events and shows what it would have produced. */
export function RulePreviewPanel({
  draftYaml,
  rule,
}: {
  readonly draftYaml: string;
  readonly rule: Rule | null;
}) {
  const [window, setWindow] = useState<string>("1h");
  const [isRunning, setIsRunning] = useState(false);
  const [run, setRun] = useState<Run | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    if (!rule) return;
    setIsRunning(true);
    setError(null);
    try {
      const {
        data,
        response,
        error: body,
      } = await apiClient.POST("/api/v1/rules/preview", {
        body: { rule, window, max_events: 50000 },
      });
      if (data) setRun({ yaml: draftYaml, window, preview: data });
      else setError(failureText(response.status, body));
    } catch (e) {
      setError(e instanceof Error ? e.message : "API unreachable");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <section
      aria-labelledby="rule-preview-title"
      className="space-y-3 rounded border border-slate-200 bg-white p-3"
    >
      <h4 id="rule-preview-title" className="font-semibold">
        Preview
      </h4>
      <div className="flex flex-wrap items-center gap-2">
        <label className="text-sm" htmlFor="preview-window">
          Window
        </label>
        <select
          id="preview-window"
          value={window}
          onChange={(e) => {
            setWindow(e.target.value);
          }}
          className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
        >
          {WINDOWS.map((w) => (
            <option key={w} value={w}>
              Last {w}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={rule === null || isRunning}
          onClick={() => void handleRun()}
          className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-40"
        >
          {isRunning ? "Running..." : "Run preview"}
        </button>
        {rule === null ? (
          <span className="text-xs text-slate-500">
            Fix the validation errors to run a preview.
          </span>
        ) : null}
        {run && run.yaml !== draftYaml ? (
          <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
            Stale: the draft changed since this run
          </span>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {error}
        </p>
      ) : null}
      {!run && !error && !isRunning ? (
        <p className="text-sm text-slate-500">No preview run yet.</p>
      ) : null}
      {run ? <RulePreviewResult preview={run.preview} /> : null}
    </section>
  );
}
