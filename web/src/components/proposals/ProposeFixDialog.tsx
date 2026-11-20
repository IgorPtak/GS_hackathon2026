import { useEffect, useState } from "react";

import type { Alert, FixKind, FixProposal, Rule } from "../../api/types";
import { RuleYamlField } from "./RuleYamlField";
import { RunbookStepForm } from "./RunbookStepForm";
import { RunbookStepPreview } from "./RunbookStepPreview";
import { EMPTY_STEP_DRAFT, buildStep, type StepDraft } from "./stepDraft";
import { useRunbookSteps } from "./useRunbookSteps";
import { useSubmitFixProposal } from "./useSubmitFixProposal";

const KINDS: readonly FixKind[] = ["threshold", "fields", "dedup_window", "runbook_step", "other"];

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

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const isRuleKind = kind === "threshold" || kind === "fields" || kind === "dedup_window";
  const isStepKind = kind === "runbook_step";
  const hasNoRunbook = isStepKind && alert.runbook_id === null;
  const step = buildStep(draft);
  const isReady =
    description.trim() !== "" &&
    !hasNoRunbook &&
    (!isRuleKind || rule !== null) &&
    (!isStepKind || step !== null);

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
    <div
      className="fixed inset-0 z-30 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-2 sm:p-6"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Propose a fix"
        onClick={(event) => {
          event.stopPropagation();
        }}
        className="w-full max-w-3xl rounded-lg bg-white p-4 shadow-xl sm:p-6"
      >
        <h2 className="text-lg font-semibold">Propose a fix</h2>
        <p className="mt-1 text-xs text-slate-500">
          Alert <span className="font-mono">{alert.id}</span> · rule{" "}
          <span className="font-mono">{alert.rule_id}</span>
        </p>
        <div className="mt-4 space-y-4">
          <label className="block text-sm">
            Fix kind
            <select
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as FixKind);
              }}
              className="w-full rounded border border-slate-300 px-2 py-1"
            >
              {KINDS.map((k) => (
                <option key={k} value={k}>
                  {k}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            Description (required)
            <textarea
              value={description}
              rows={3}
              onChange={(event) => {
                setDescription(event.target.value);
              }}
              className="w-full rounded border border-slate-300 px-2 py-1"
            />
          </label>
          {isRuleKind ? (
            <RuleYamlField
              ruleId={alert.rule_id}
              serverErrors={sender.details}
              onRuleChange={setRule}
            />
          ) : null}
          {hasNoRunbook ? (
            <p className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
              This alert has no runbook, so a runbook step cannot be proposed.
            </p>
          ) : null}
          {isStepKind && !hasNoRunbook ? (
            <>
              <RunbookStepForm
                draft={draft}
                stepCount={runbook.steps?.length ?? 0}
                onChange={setDraft}
              />
              {runbook.isLoading ? (
                <p className="text-sm text-slate-500">Loading runbook...</p>
              ) : null}
              {runbook.error ? <p className="text-sm text-red-700">{runbook.error}</p> : null}
              {runbook.steps && step ? (
                <RunbookStepPreview steps={runbook.steps} step={step} />
              ) : null}
            </>
          ) : null}
        </div>
        {sender.message ? (
          <div role="alert" className="mt-4 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
            <p>{sender.message}</p>
            {!isRuleKind && sender.details.length > 0 ? (
              <ul className="mt-1 space-y-1">
                {sender.details.map((d, i) => (
                  <li key={i}>
                    <code className="font-mono font-semibold">{d.path || "(root)"}</code>:{" "}
                    {d.message}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ) : null}
        <div className="mt-4 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={!isReady || sender.isSubmitting}
            onClick={() => {
              void handleSubmit();
            }}
            className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          >
            {sender.isSubmitting ? "Sending..." : "Send proposal"}
          </button>
        </div>
      </div>
    </div>
  );
}
