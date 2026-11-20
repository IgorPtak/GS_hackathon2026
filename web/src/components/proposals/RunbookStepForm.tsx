import type { StepKind } from "../../api/types";
import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { Icon } from "../ui/icons";
import { Select } from "../ui/Select";
import { TextInput } from "../ui/TextInput";
import { STEP_KIND_OPTIONS } from "./fixLabels";
import type { ParamRow, StepDraft } from "./stepDraft";
import { useActionIds } from "./useActionIds";

interface RunbookStepFormProps {
  readonly draft: StepDraft;
  readonly stepCount: number;
  readonly onChange: (draft: StepDraft) => void;
}

/** Fields of one new runbook step: position, kind, text, optional action and its params. */
export function RunbookStepForm({ draft, stepCount, onChange }: RunbookStepFormProps) {
  const actions = useActionIds();
  const actionOptions = [
    { value: "", label: "None" },
    ...actions.map((id) => ({ value: id, label: id })),
  ];

  const setParam = (i: number, row: ParamRow) => {
    onChange({ ...draft, params: draft.params.map((p, k) => (k === i ? row : p)) });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label={`Position (0 to ${String(stepCount)})`}>
          {(props) => (
            <TextInput
              {...props}
              type="number"
              min={0}
              max={stepCount}
              value={draft.index}
              onChange={(event) => {
                onChange({ ...draft, index: Math.max(0, Number(event.target.value) || 0) });
              }}
            />
          )}
        </Field>
        <Field label="Step type">
          {(props) => (
            <Select
              {...props}
              options={STEP_KIND_OPTIONS}
              value={draft.kind}
              onChange={(value) => {
                onChange({ ...draft, kind: value as StepKind });
              }}
            />
          )}
        </Field>
      </div>

      <Field label="Step instruction">
        {(props) => (
          <TextInput
            {...props}
            type="text"
            placeholder="Describe what should happen at this step"
            value={draft.text}
            onChange={(event) => {
              onChange({ ...draft, text: event.target.value });
            }}
          />
        )}
      </Field>

      <Field label="Action (optional)">
        {(props) => (
          <Select
            {...props}
            options={actionOptions}
            value={draft.action}
            onChange={(value) => {
              onChange({ ...draft, action: value });
            }}
          />
        )}
      </Field>

      {draft.action !== "" ? (
        <div className="space-y-2.5">
          <p className="text-meta font-medium text-ink">Action parameters</p>
          {draft.params.map((row, i) => (
            <div key={i} className="flex items-center gap-2">
              <TextInput
                aria-label="Parameter key"
                placeholder="Key"
                value={row.key}
                onChange={(event) => {
                  setParam(i, { ...row, key: event.target.value });
                }}
              />
              <TextInput
                aria-label="Parameter value"
                placeholder="Value"
                value={row.value}
                onChange={(event) => {
                  setParam(i, { ...row, value: event.target.value });
                }}
              />
              <button
                type="button"
                aria-label="Remove parameter"
                onClick={() => {
                  onChange({ ...draft, params: draft.params.filter((_, k) => k !== i) });
                }}
                className="flex size-10 shrink-0 items-center justify-center rounded-input bg-fill text-ink-2 hover:bg-hairline hover:text-ink"
              >
                <Icon name="cross" size={16} />
              </button>
            </div>
          ))}
          <Button
            variant="secondary"
            icon="plus"
            onClick={() => {
              onChange({ ...draft, params: [...draft.params, { key: "", value: "" }] });
            }}
          >
            Add parameter
          </Button>
        </div>
      ) : null}
    </div>
  );
}
