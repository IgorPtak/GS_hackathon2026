import type { StepKind } from "../../api/types";
import type { ParamRow, StepDraft } from "./stepDraft";
import { useActionIds } from "./useActionIds";

const KINDS: readonly StepKind[] = ["text", "check", "action"];
const FIELD = "w-full rounded border border-slate-300 px-2 py-1 text-sm";

interface RunbookStepFormProps {
  readonly draft: StepDraft;
  readonly stepCount: number;
  readonly onChange: (draft: StepDraft) => void;
}

/** Fields of one new runbook step: position, kind, text, optional action and its params. */
export function RunbookStepForm({ draft, stepCount, onChange }: RunbookStepFormProps) {
  const actions = useActionIds();
  const setParam = (i: number, row: ParamRow) => {
    onChange({ ...draft, params: draft.params.map((p, k) => (k === i ? row : p)) });
  };
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <label className="block text-sm">
          Position (0 to {stepCount})
          <input
            type="number"
            min={0}
            max={stepCount}
            value={draft.index}
            onChange={(event) => {
              onChange({ ...draft, index: Math.max(0, Number(event.target.value) || 0) });
            }}
            className={FIELD}
          />
        </label>
        <label className="block text-sm">
          Step kind
          <select
            value={draft.kind}
            onChange={(event) => {
              onChange({ ...draft, kind: event.target.value as StepKind });
            }}
            className={FIELD}
          >
            {KINDS.map((kind) => (
              <option key={kind} value={kind}>
                {kind}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="block text-sm">
        Step text
        <input
          type="text"
          value={draft.text}
          onChange={(event) => {
            onChange({ ...draft, text: event.target.value });
          }}
          className={FIELD}
        />
      </label>
      <label className="block text-sm">
        Action (optional)
        <select
          value={draft.action}
          onChange={(event) => {
            onChange({ ...draft, action: event.target.value });
          }}
          className={FIELD}
        >
          <option value="">None</option>
          {actions.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
      </label>
      {draft.action !== "" ? (
        <div className="space-y-2">
          <p className="text-sm">Params</p>
          {draft.params.map((row, i) => (
            <div key={i} className="flex gap-2">
              <input
                aria-label="Param key"
                placeholder="key"
                value={row.key}
                onChange={(event) => {
                  setParam(i, { ...row, key: event.target.value });
                }}
                className={FIELD}
              />
              <input
                aria-label="Param value"
                placeholder="value"
                value={row.value}
                onChange={(event) => {
                  setParam(i, { ...row, value: event.target.value });
                }}
                className={FIELD}
              />
              <button
                type="button"
                aria-label="Remove param"
                onClick={() => {
                  onChange({ ...draft, params: draft.params.filter((_, k) => k !== i) });
                }}
                className="rounded border border-slate-300 px-2 text-sm"
              >
                ×
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() => {
              onChange({ ...draft, params: [...draft.params, { key: "", value: "" }] });
            }}
            className="rounded border border-slate-300 px-2 py-1 text-sm"
          >
            Add param
          </button>
        </div>
      ) : null}
    </div>
  );
}
