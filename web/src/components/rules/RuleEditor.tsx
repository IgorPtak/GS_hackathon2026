import { useState } from "react";

import type { ConfigValidationError, RuleRecord } from "../../api/types";
import { useConfigLists } from "../recipients/useConfigLists";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Segmented } from "../ui/Segmented";
import { StatusChip } from "../ui/StatusChip";
import { RulePreviewPanel } from "./RulePreviewPanel";
import { RuleRouteStep } from "./RuleRouteStep";
import { RuleWhenStep } from "./RuleWhenStep";
import { ValidationErrorList } from "./ValidationErrorList";
import { YamlEditor } from "./YamlEditor";
import { isConditionFieldError } from "./ruleErrors";
import { useRuleDraft, type RuleSource } from "./useRuleDraft";
import { parseWhenFromRuleYaml } from "./conditionYaml";

type Step = "when" | "route" | "preview";

const STEPS = [
  { value: "when", label: "When" },
  { value: "route", label: "Who & how" },
  { value: "preview", label: "Preview" },
];

interface RuleEditorProps {
  readonly source: RuleSource;
  readonly version: number | null;
  readonly team: string;
  readonly onSaved: (record: RuleRecord) => void;
}

/** The 3-step flow for one rule; the YAML under "Advanced" is the same text, kept in sync. */
export function RuleEditor({ source, version, team, onSaved }: RuleEditorProps) {
  const [step, setStep] = useState<Step>("when");
  const draft = useRuleDraft(source, team, onSaved);
  const { config } = useConfigLists();
  const { text, validation } = draft;
  const errors = draft.shownErrors;
  const isNew = source.id === null;
  const hasForm = parseWhenFromRuleYaml(text).kind === "form";
  const isShownAtField = (e: ConfigValidationError) =>
    step === "when" && (e.path === "id" || e.path === "description");
  const listed = errors.filter(
    (e) => !isShownAtField(e) && !(step === "when" && hasForm && isConditionFieldError(e)),
  );
  const names = Object.fromEntries((config?.recipients ?? []).map((r) => [r.id, r.display_name]));
  const title = source.id === null ? "New rule" : source.id;

  return (
    <Card className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-card-title font-semibold break-all">{title}</h2>
        {version === null ? null : <StatusChip tone="success">Active version {version}</StatusChip>}
        {draft.isChanged ? <StatusChip tone="warning">Unsaved changes</StatusChip> : null}
      </div>
      <Segmented
        label="Rule steps"
        options={STEPS}
        value={step}
        onChange={(value) => {
          setStep(value as Step);
        }}
      />
      {step === "when" ? (
        <RuleWhenStep yaml={text} isNew={isNew} errors={errors} onChange={draft.edit} />
      ) : null}
      {step === "route" ? (
        <RuleRouteStep yaml={text} ownerTeam={team} config={config} onChange={draft.edit} />
      ) : null}
      {step === "preview" ? (
        <RulePreviewPanel
          draftYaml={text}
          rule={draft.isValid ? validation.rule : null}
          names={names}
        />
      ) : null}
      <ValidationErrorList
        errors={listed}
        isChecking={validation.isChecking}
        isValid={draft.isValid}
        requestError={validation.requestError}
      />
      {draft.saveMessage ? (
        <p
          role="alert"
          className="rounded-tile bg-critical/12 px-4 py-3 text-body text-critical-ink"
        >
          {draft.saveMessage}
        </p>
      ) : null}
      <details className="rounded-tile border border-hairline">
        <summary className="cursor-pointer px-4 py-3 text-body font-medium">
          Advanced (YAML)
        </summary>
        <div className="space-y-2 px-4 pb-4">
          <p className="text-meta text-ink-2">
            The same rule as text. Changes here show up in the steps above, and the other way round.
          </p>
          <YamlEditor value={text} errorLines={draft.lines} onChange={draft.edit} />
        </div>
      </details>
      <StepFooter
        step={step}
        canSave={draft.isValid && (draft.isChanged || isNew)}
        hint={
          draft.isValid
            ? draft.isChanged || isNew
              ? null
              : "No changes to save."
            : "Fix the problems above to save."
        }
        isSaving={draft.isSaving}
        isChanged={draft.isChanged}
        onStep={setStep}
        onSave={() => void draft.save()}
        onRevert={() => {
          draft.edit(source.yaml);
        }}
      />
    </Card>
  );
}

interface StepFooterProps {
  readonly step: Step;
  readonly canSave: boolean;
  readonly isSaving: boolean;
  readonly isChanged: boolean;
  readonly hint: string | null;
  readonly onStep: (step: Step) => void;
  readonly onSave: () => void;
  readonly onRevert: () => void;
}

function StepFooter({
  step,
  canSave,
  isSaving,
  isChanged,
  hint,
  onStep,
  onSave,
  onRevert,
}: StepFooterProps) {
  const back: Step | null = step === "route" ? "when" : step === "preview" ? "route" : null;
  const next: Step | null = step === "when" ? "route" : step === "route" ? "preview" : null;
  return (
    <div className="sticky bottom-0 -mx-6 -mb-6 flex flex-wrap items-center gap-2 rounded-b-card border-t border-hairline bg-card px-6 py-4">
      {back ? (
        <Button
          onClick={() => {
            onStep(back);
          }}
        >
          Back
        </Button>
      ) : null}
      {next ? (
        <Button
          variant="primary"
          onClick={() => {
            onStep(next);
          }}
        >
          Next
        </Button>
      ) : (
        <Button variant="primary" isLoading={isSaving} disabled={!canSave} onClick={onSave}>
          Save rule
        </Button>
      )}
      <Button variant="ghost" disabled={!isChanged || isSaving} onClick={onRevert}>
        Revert changes
      </Button>
      {step === "preview" && hint ? <span className="text-meta text-ink-2">{hint}</span> : null}
    </div>
  );
}
