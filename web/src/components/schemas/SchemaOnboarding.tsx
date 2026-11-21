import { useState } from "react";

import { IllustratedBanner } from "../ui/IllustratedBanner";

import { useEventStream } from "../../hooks/useEventStream";
import { Icon } from "../ui/icons";
import { Stepper } from "../ui/Stepper";
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

const STEP_NAMES = ["Pick a sample", "Check the mapping", "Test and save"];

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

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      {step === 1 ? (
        <IllustratedBanner scene="connect" title="Connect a system" focus="75% 45%">
          Show Beacon one event from your system. It suggests how to read it, you check it, and
          alerts can use it right away.
        </IllustratedBanner>
      ) : null}
      <Stepper
        label="Connect a system"
        steps={STEP_NAMES}
        current={step}
        onBack={(next) => {
          if (next === 1 || next === 2) setStep(next);
        }}
      />
      <div key={step} className="animate-fade-up">
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
      </div>
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
