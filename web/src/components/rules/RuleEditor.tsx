import { useMemo, useState } from "react";

import { apiClient } from "../../api/client";
import type { ConfigValidationError, RuleRecord } from "../../api/types";
import { RuleConditionForm } from "./RuleConditionForm";
import { RulePreviewPanel } from "./RulePreviewPanel";
import { ValidationErrorList } from "./ValidationErrorList";
import { YamlEditor } from "./YamlEditor";
import { detailsFromBody, errorLines, messageFromBody } from "./ruleErrors";
import { useRuleValidation } from "./useRuleValidation";

interface RuleEditorProps {
  readonly record: RuleRecord;
  readonly team: string;
  readonly onSaved: (record: RuleRecord) => void;
}

/** Edits one rule as YAML with live validation, preview and save-as-new-version. */
export function RuleEditor({ record, team, onSaved }: RuleEditorProps) {
  const [text, setText] = useState(record.yaml);
  const [isSaving, setIsSaving] = useState(false);
  const [saveErrors, setSaveErrors] = useState<ConfigValidationError[]>([]);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const validation = useRuleValidation(text);

  const isChanged = text !== record.yaml;
  const isValid = !validation.isChecking && validation.rule !== null;
  const shownErrors = saveErrors.length > 0 ? saveErrors : validation.errors;
  const lines = useMemo(() => errorLines(text, shownErrors), [text, shownErrors]);

  function handleChange(value: string) {
    setText(value);
    setSaveErrors([]);
    setSaveMessage(null);
  }

  async function handleSave() {
    if (!validation.rule) return;
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const { data, error } = await apiClient.PUT("/api/v1/rules/{rule_id}", {
        params: { path: { rule_id: record.id } },
        body: { rule: validation.rule, actor: { id: `${team}-operator`, display_name: null } },
      });
      if (data) onSaved(data);
      else {
        const details = detailsFromBody(error);
        setSaveErrors(details);
        setSaveMessage(messageFromBody(error, "Save failed"));
      }
    } catch (e) {
      setSaveMessage(e instanceof Error ? e.message : "API unreachable");
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold break-all">{record.id}</h3>
        <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-white">
          Active version v{record.version}
        </span>
        {isChanged ? <span className="text-xs text-amber-700">Unsaved changes</span> : null}
      </div>
      <RuleConditionForm yaml={text} onChange={handleChange} />
      <YamlEditor value={text} errorLines={lines} onChange={handleChange} />
      <ValidationErrorList
        errors={shownErrors}
        isChecking={validation.isChecking}
        isValid={isValid}
        requestError={validation.requestError}
      />
      {saveMessage ? (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {saveMessage}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!isValid || !isChanged || isSaving}
          onClick={() => void handleSave()}
          className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-40"
        >
          {isSaving ? "Saving..." : "Save"}
        </button>
        <button
          type="button"
          disabled={!isChanged || isSaving}
          onClick={() => {
            handleChange(record.yaml);
          }}
          className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm disabled:opacity-40"
        >
          Revert
        </button>
      </div>
      <RulePreviewPanel draftYaml={text} rule={isValid ? validation.rule : null} />
    </div>
  );
}
