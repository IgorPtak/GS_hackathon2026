import { useState } from "react";

import type { ConfigValidationError, RuleRecord } from "../../api/types";
import { useConfigLists } from "../recipients/useConfigLists";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Icon } from "../ui/icons";
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

const NO_LINES: readonly number[] = [];

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
  const isNew = source.id === null;
  // A blank new rule should not greet anyone in red: show problems once they start or move on.
  const [hasMovedOn, setHasMovedOn] = useState(false);
  const isQuiet = isNew && !draft.isChanged && !hasMovedOn;
  const errors = isQuiet ? [] : draft.shownErrors;
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
          setHasMovedOn(true);
          setStep(value as Step);
        }}
      />
      <div key={step} className="animate-fade-up">
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
      </div>
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
      <details className="group rounded-tile border border-hairline transition-colors open:bg-fill/30">
        <summary className="flex list-none items-center gap-2 rounded-tile px-4 py-3 text-body font-medium transition-colors hover:bg-fill/60">
          <Icon
            name="chevron"
            size={16}
            className="-rotate-90 text-ink-2 transition-transform duration-300 group-open:rotate-0"
          />
          Advanced
          <span className="text-meta font-normal text-ink-2">edit as YAML</span>
        </summary>
        <div className="space-y-2 px-4 pb-4">
          <p className="text-meta text-ink-2">
            The same rule as text. Changes here show up in the steps above, and the other way round.
          </p>
          <YamlEditor
            value={text}
            errorLines={isQuiet ? NO_LINES : draft.lines}
            onChange={draft.edit}
          />
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
        onStep={(next) => {
          setHasMovedOn(true);
          setStep(next);
        }}
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
    <div className="-mx-6 -mb-6 flex flex-wrap items-center gap-2 rounded-b-card border-t border-hairline px-6 py-4">
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
