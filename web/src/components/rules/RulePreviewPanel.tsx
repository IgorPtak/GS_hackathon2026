import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { Rule, RulePreview } from "../../api/types";
import { Button } from "../ui/Button";
import { Segmented } from "../ui/Segmented";
import { Skeleton } from "../ui/Skeleton";
import { StatusChip } from "../ui/StatusChip";
import { RulePreviewResult } from "./RulePreviewResult";
import { messageFromBody } from "./ruleErrors";

const WINDOWS = [
  { value: "15m", label: "15 min" },
  { value: "1h", label: "1 hour" },
  { value: "6h", label: "6 hours" },
  { value: "24h", label: "24 hours" },
];

interface Outcome {
  readonly key: string;
  readonly error: string | null;
  readonly run: Run | null;
}

interface Run {
  readonly yaml: string;
  readonly window: string;
  readonly preview: RulePreview;
}

function failureText(status: number, body: unknown): string {
  if (status === 404 || status === 503) return "Preview is not available yet on this server.";
  return messageFromBody(body, `Preview failed (API error ${String(status)}). Try again.`);
}

/** Runs the draft rule over the last window of events and shows what it would have produced. */
export function RulePreviewPanel({
  draftYaml,
  rule,
  names,
}: {
  readonly draftYaml: string;
  readonly rule: Rule | null;
  readonly names: Readonly<Record<string, string>>;
}) {
  const [window, setWindow] = useState<string>("1h");
  const [nonce, setNonce] = useState(0);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const key = `${draftYaml}\n${window}\n${String(nonce)}`;
  const isRunning = rule !== null && outcome?.key !== key;
  const run = outcome?.run ?? null;
  const error = outcome?.key === key ? outcome.error : null;

  // Runs on entering the step and whenever the window changes or "Run again" is pressed.
  useEffect(() => {
    if (!rule) return;
    let isCancelled = false;
    apiClient
      .POST("/api/v1/rules/preview", { body: { rule, window, max_events: 50000 } })
      .then(({ data, response, error: body }) => {
        if (isCancelled) return;
        if (data) setOutcome({ key, error: null, run: { yaml: draftYaml, window, preview: data } });
        else
          setOutcome((prev) => ({
            key,
            error: failureText(response.status, body),
            run: prev?.run ?? null,
          }));
      })
      .catch((e: unknown) => {
        if (isCancelled) return;
        const text = e instanceof Error ? e.message : "API unreachable";
        setOutcome((prev) => ({ key, error: text, run: prev?.run ?? null }));
      });
    return () => {
      isCancelled = true;
    };
    // `rule` identity changes with every validation; the draft text is what matters here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return (
    <section aria-label="Rule preview" className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented label="Preview window" options={WINDOWS} value={window} onChange={setWindow} />
        <Button
          icon="retry"
          isLoading={isRunning}
          disabled={rule === null}
          onClick={() => {
            setNonce((n) => n + 1);
          }}
        >
          Run again
        </Button>
        {run && run.yaml !== draftYaml ? (
          <StatusChip tone="warning">Out of date: the rule changed since this run</StatusChip>
        ) : null}
      </div>
      {rule === null ? (
        <p className="rounded-tile bg-fill px-4 py-3 text-body text-ink-2">
          Fix the problems listed below to see what this rule would do.
        </p>
      ) : null}
      {error ? (
        <p
          role="alert"
          className="rounded-tile bg-critical/12 px-4 py-3 text-body text-critical-ink"
        >
          {error}
        </p>
      ) : null}
      {isRunning && !run ? <Skeleton className="h-28 w-full" /> : null}
      {run ? (
        <div aria-busy={isRunning} className={isRunning ? "opacity-60" : undefined}>
          <RulePreviewResult preview={run.preview} window={run.window} names={names} />
        </div>
      ) : null}
    </section>
  );
}
