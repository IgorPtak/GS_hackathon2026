import { useState } from "react";

import type { Alert, FixKind, FixProposal, Rule } from "../../api/types";
import { cx } from "../../lib/cx";
import { Button } from "../ui/Button";
import { CONTROL_CLASS } from "../ui/controlStyles";
import { Dialog } from "../ui/Dialog";
import { Field } from "../ui/Field";
import { Select } from "../ui/Select";
import { Skeleton } from "../ui/Skeleton";
import { FIX_KIND_OPTIONS } from "./fixLabels";
import { RuleYamlField } from "./RuleYamlField";
import { RunbookStepForm } from "./RunbookStepForm";
import { RunbookStepPreview } from "./RunbookStepPreview";
import { EMPTY_STEP_DRAFT, buildStep, draftFromStep, type StepDraft } from "./stepDraft";
import { useDraftFixProposal } from "./useDraftFixProposal";
import { useRunbookSteps } from "./useRunbookSteps";
import { useSubmitFixProposal } from "./useSubmitFixProposal";
import { toYamlLines } from "./yamlLite";

interface ProposeFixDialogProps {
  readonly alert: Pick<Alert, "id" | "rule_id" | "team" | "runbook_id">;
  readonly onClose: () => void;
  readonly onCreated: (proposal: FixProposal) => void;
}

/** Modal to propose a fix from an alert: edited rule, a new runbook step, or free text. */
export function ProposeFixDialog({ alert, onClose, onCreated }: ProposeFixDialogProps) {
  const [kind, setKind] = useState<FixKind>("threshold");
  const [description, setDescription] = useState("");
  const [rule, setRule] = useState<Rule | null>(null);
  const [draft, setDraft] = useState<StepDraft>(EMPTY_STEP_DRAFT);
  const runbook = useRunbookSteps(kind === "runbook_step" ? alert.runbook_id : null);
  const sender = useSubmitFixProposal(alert.id, alert.team);
  const drafter = useDraftFixProposal(alert.id);
  const [prefill, setPrefill] = useState<{ yaml: string; nonce: number } | null>(null);

  const isRuleKind = kind === "threshold" || kind === "fields" || kind === "dedup_window";
  const isStepKind = kind === "runbook_step";
  const hasNoRunbook = isStepKind && alert.runbook_id === null;
  const step = buildStep(draft);
  const isReady =
    description.trim() !== "" &&
    !hasNoRunbook &&
    (!isRuleKind || rule !== null) &&
    (!isStepKind || step !== null);

  async function handleDraft() {
    const suggestion = await drafter.draft();
    if (!suggestion) return;
    setKind(suggestion.kind);
    setDescription(suggestion.description);
    if (suggestion.proposed_rule) {
      const yaml = toYamlLines(suggestion.proposed_rule).join("\n");
      setPrefill((previous) => ({ yaml, nonce: (previous?.nonce ?? 0) + 1 }));
    }
    if (suggestion.proposed_runbook_step) setDraft(draftFromStep(suggestion.proposed_runbook_step));
  }

  async function handleSubmit() {
    const created = await sender.submit({
      kind,
      description: description.trim(),
      proposed_rule: isRuleKind ? rule : null,
      proposed_runbook_step: isStepKind ? step : null,
    });
    if (created) onCreated(created);
  }

  return (
    <Dialog
      isOpen
      onClose={onClose}
      title="Propose a fix"
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            disabled={!isReady}
            isLoading={sender.isSubmitting}
            onClick={() => {
              void handleSubmit();
            }}
          >
            {sender.isSubmitting ? "Sending…" : "Send proposal"}
          </Button>
        </>
      }
    >
      <div className="max-h-[68vh] space-y-4 overflow-y-auto pr-1">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-meta text-ink-2">
            Rule <span className="font-mono text-ink">{alert.rule_id}</span>
          </p>
          <Button
            variant="secondary"
            icon="sparkles"
            isLoading={drafter.isDrafting}
            onClick={() => {
              void handleDraft();
            }}
          >
            {drafter.isDrafting ? "Drafting…" : "Draft with AI"}
          </Button>
        </div>

        {drafter.message ? (
          <p
            role="alert"
            className="rounded-tile border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-meta text-warning-ink"
          >
            {drafter.message}
          </p>
        ) : null}

        <Field label="What should change">
          {(props) => (
            <Select
              {...props}
              options={FIX_KIND_OPTIONS}
              value={kind}
              onChange={(value) => {
                setKind(value as FixKind);
              }}
            />
          )}
        </Field>

        <Field label="Why this helps">
          {(props) => (
            <textarea
              {...props}
              rows={3}
              value={description}
              placeholder="Explain what this change prevents or improves"
              onChange={(event) => {
                setDescription(event.target.value);
              }}
              className={cx(CONTROL_CLASS, "h-auto py-2.5")}
            />
          )}
        </Field>

        {isRuleKind ? (
          <RuleYamlField
            ruleId={alert.rule_id}
            serverErrors={sender.details}
            onRuleChange={setRule}
            prefill={prefill}
          />
        ) : null}

        {hasNoRunbook ? (
          <p className="rounded-tile border border-warning/30 bg-warning/10 px-3.5 py-2.5 text-meta text-warning-ink">
            This alert has no attached runbook, so a runbook step cannot be proposed.
          </p>
        ) : null}

        {isStepKind && !hasNoRunbook ? (
          <div className="space-y-3">
            <RunbookStepForm
              draft={draft}
              stepCount={runbook.steps?.length ?? 0}
              onChange={setDraft}
            />
            {runbook.isLoading ? <Skeleton className="h-20 w-full" /> : null}
            {runbook.error ? (
              <p role="alert" className="text-meta text-critical-ink">
                {runbook.error}
              </p>
            ) : null}
            {runbook.steps && step ? (
              <RunbookStepPreview steps={runbook.steps} step={step} />
            ) : null}
          </div>
        ) : null}

        {sender.message ? (
          <div
            role="alert"
            className="rounded-tile border border-critical/30 bg-critical/8 px-3.5 py-2.5 text-meta text-critical-ink"
          >
            <p>{sender.message}</p>
            {!isRuleKind && sender.details.length > 0 ? (
              <ul className="mt-1.5 space-y-1">
                {sender.details.map((d, i) => (
                  <li key={i}>
                    <code className="font-mono font-medium">{d.path || "(root)"}</code>: {d.message}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </Dialog>
  );
}
