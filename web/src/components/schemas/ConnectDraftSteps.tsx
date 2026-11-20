import { isValidProfileId, flattenKeyPaths, type SampleEvent } from "./schemaDraft";
import { MappingStep } from "./MappingStep";
import { TestSaveStep } from "./TestSaveStep";
import { useSchemaDraft } from "./useSchemaDraft";

interface ConnectDraftStepsProps {
  readonly step: 2 | 3;
  readonly sample: SampleEvent;
  readonly team: string | null;
  readonly onStep: (step: 1 | 2 | 3) => void;
  readonly onSaved: () => void;
  readonly onCreateRule: () => void;
}

/** Steps 2 and 3 share one draft, so editing the mapping and testing it keep the same state. */
export function ConnectDraftSteps({
  step,
  sample,
  team,
  onStep,
  onSaved,
  onCreateRule,
}: ConnectDraftStepsProps) {
  const draft = useSchemaDraft(sample, team);
  const { profile } = draft;
  if (step === 2) {
    return (
      <MappingStep
        profile={profile}
        proposal={draft.proposal}
        proposeError={draft.proposeError}
        paths={flattenKeyPaths(sample)}
        errors={draft.saveErrors}
        onChange={draft.updateProfile}
        onBack={() => {
          onStep(1);
        }}
        onNext={() => {
          if (draft.isStale) draft.runTest();
          onStep(3);
        }}
      />
    );
  }
  return (
    <TestSaveStep
      result={draft.test.result}
      isStale={draft.isStale}
      isRunning={draft.test.isRunning}
      testError={draft.test.error}
      saved={draft.saved}
      isSaving={draft.isSaving}
      saveMessage={draft.saveMessage}
      saveErrors={draft.saveErrors}
      canSave={profile !== null && isValidProfileId(profile.id) && team !== null}
      onRetest={draft.runTest}
      onBack={() => {
        onStep(2);
      }}
      onSave={draft.save}
      onCreateRule={onCreateRule}
      onDone={onSaved}
    />
  );
}
