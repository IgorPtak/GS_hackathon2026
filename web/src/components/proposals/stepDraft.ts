import type { RunbookStep, StepKind } from "../../api/types";

export interface ParamRow {
  readonly key: string;
  readonly value: string;
}

export interface StepDraft {
  readonly index: number;
  readonly kind: StepKind;
  readonly text: string;
  readonly action: string;
  readonly params: readonly ParamRow[];
}

export const EMPTY_STEP_DRAFT: StepDraft = {
  index: 0,
  kind: "text",
  text: "",
  action: "",
  params: [],
};

/** Builds the API step from the form; null while the text is empty. */
export function buildStep(draft: StepDraft): RunbookStep | null {
  if (draft.text.trim() === "") return null;
  const params: Record<string, string> = {};
  for (const row of draft.params) if (row.key.trim() !== "") params[row.key.trim()] = row.value;
  return {
    index: draft.index,
    kind: draft.kind,
    text: draft.text.trim(),
    action: draft.action === "" ? null : draft.action,
    params,
    approval: null,
    is_automatic: false,
    run_if: "always",
    max_attempts: 1,
  };
}
