import { useState } from "react";

import { useEventStream } from "../../hooks/useEventStream";
import { Icon } from "../ui/icons";
import { Segmented } from "../ui/Segmented";
import { ConnectDraftSteps } from "./ConnectDraftSteps";
import { SampleStep } from "./SampleStep";
import type { SampleEvent } from "./schemaDraft";
import { useSchemaProfiles, useUnknownSchemas } from "./useSchemaLists";
import { SchemaProfileList } from "./SchemaProfileList";

interface SchemaOnboardingProps {
  readonly teamId: string | null;
  readonly onCreateRule: () => void;
}

interface Picked {
  readonly sample: SampleEvent;
  readonly nonce: number;
}

type Step = 1 | 2 | 3;

const STEP_OPTIONS = [
  { value: "1", label: "1\u00a0Sample" },
  { value: "2", label: "2\u00a0Mapping" },
  { value: "3", label: "3\u00a0Test\u00a0&\u00a0save" },
];

/** Sample -> mapping -> test & save, with the saved mappings listed under "Advanced". */
export function SchemaOnboarding({ teamId, onCreateRule }: SchemaOnboardingProps) {
  const [picked, setPicked] = useState<Picked | null>(null);
  const [step, setStep] = useState<Step>(1);
  const inbox = useUnknownSchemas();
  const profiles = useSchemaProfiles();
  useEventStream(teamId, {
    "unknown_schema.detected": inbox.reload,
    "config.changed": profiles.reload,
    onReconnect: () => {
      inbox.reload();
      profiles.reload();
    },
  });

  function reset() {
    setPicked(null);
    setStep(1);
    profiles.reload();
    inbox.reload();
  }

  // Later steps are only reachable once a sample is picked; going back is always allowed.
  const highest = picked ? 3 : 1;
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Segmented
        label="Steps"
        value={String(step)}
        options={STEP_OPTIONS}
        onChange={(value) => {
          const next = Number(value);
          if (next <= highest && (next === 1 || next === 2 || next === 3)) setStep(next);
        }}
      />
      {step === 1 || !picked ? (
        <SampleStep
          samples={inbox.items}
          isLoading={inbox.isLoading}
          error={inbox.error}
          onPick={(sample) => {
            setPicked((p) => ({ sample, nonce: (p?.nonce ?? 0) + 1 }));
            setStep(2);
          }}
        />
      ) : (
        <ConnectDraftSteps
          key={picked.nonce}
          step={step === 3 ? 3 : 2}
          sample={picked.sample}
          team={teamId}
          onStep={setStep}
          onSaved={reset}
          onCreateRule={onCreateRule}
        />
      )}
      <details className="group rounded-card border border-hairline bg-card px-6 py-4">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-body font-semibold">
          <Icon
            name="chevron"
            size={16}
            className="-rotate-90 transition-transform group-open:rotate-0"
          />
          Advanced
          <span className="text-meta font-normal text-ink-2 max-sm:hidden">saved mappings</span>
        </summary>
        <div className="mt-4">
          <SchemaProfileList
            profiles={profiles.items}
            isLoading={profiles.isLoading}
            error={profiles.error}
          />
        </div>
      </details>
    </div>
  );
}
