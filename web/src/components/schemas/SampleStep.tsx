import { useState } from "react";

import type { UnknownSchemaSample } from "../../api/types";
import { Card } from "../ui/Card";
import { EmptyState } from "../ui/EmptyState";
import { Segmented } from "../ui/Segmented";
import { Skeleton } from "../ui/Skeleton";
import { PasteSampleForm } from "./PasteSampleForm";
import type { SampleEvent } from "./schemaDraft";
import { UnknownSampleRow } from "./UnknownSampleRow";

interface SampleStepProps {
  readonly samples: readonly UnknownSchemaSample[];
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly onPick: (sample: SampleEvent, label: string) => void;
}

/** Step 1: pick a recently seen unknown event or paste one. */
export function SampleStep({ samples, isLoading, error, onPick }: SampleStepProps) {
  const [mode, setMode] = useState<"seen" | "paste">("seen");
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-card-title font-semibold">Which event should Beacon learn?</h2>
        <p className="mt-1 text-body text-ink-2">
          Pick an event your system already sent, or paste one.
        </p>
      </div>
      <Segmented
        label="Where the sample comes from"
        value={mode}
        options={[
          { value: "seen", label: `Recently seen unknown events (${String(samples.length)})` },
          { value: "paste", label: "Paste a sample event" },
        ]}
        onChange={(v) => {
          setMode(v === "paste" ? "paste" : "seen");
        }}
      />
      {mode === "paste" ? (
        <Card>
          <PasteSampleForm
            onPick={(sample) => {
              onPick(sample, "pasted event");
            }}
          />
        </Card>
      ) : (
        <Card isPadded={false}>
          {isLoading ? (
            <div className="space-y-3 p-5" aria-label="Loading unknown events">
              <Skeleton className="h-12" />
              <Skeleton className="h-12" />
            </div>
          ) : null}
          {error ? (
            <p role="alert" className="p-5 text-body text-critical-ink">
              Beacon could not load unknown events ({error}). Check that the API is running, then
              reload.
            </p>
          ) : null}
          {!isLoading && !error && samples.length === 0 ? (
            <EmptyState icon="connect">
              Nothing unknown has arrived yet. Send an event from your system, or paste one.
            </EmptyState>
          ) : null}
          <ul className="divide-y divide-hairline">
            {samples.map((s) => (
              <UnknownSampleRow
                key={s.shape_hash}
                sample={s}
                onPick={() => {
                  onPick(s.sample_event, s.source_id);
                }}
              />
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
