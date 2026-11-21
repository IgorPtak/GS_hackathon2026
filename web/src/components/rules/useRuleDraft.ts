import { useMemo, useState } from "react";

import { apiClient } from "../../api/client";
import type { ConfigValidationError, RuleRecord } from "../../api/types";
import { detailsFromBody, errorLines, messageFromBody, tidyErrors } from "./ruleErrors";
import { useRuleValidation } from "./useRuleValidation";

/** The YAML being edited. `id` is null for a rule that does not exist yet. */
export interface RuleSource {
  readonly id: string | null;
  readonly yaml: string;
}

/** Draft text with live validation, and saving as a new version (PUT /api/v1/rules/{id}). */
export function useRuleDraft(
  source: RuleSource,
  team: string,
  onSaved: (record: RuleRecord) => void,
) {
  const [text, setText] = useState(source.yaml);
  const [isSaving, setIsSaving] = useState(false);
  const [saveErrors, setSaveErrors] = useState<ConfigValidationError[]>([]);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const validation = useRuleValidation(text);

  const isChanged = text !== source.yaml;
  const isValid = !validation.isChecking && validation.rule !== null;
  const shownErrors = useMemo(
    () => tidyErrors(saveErrors.length > 0 ? saveErrors : validation.errors),
    [saveErrors, validation.errors],
  );
  const lines = useMemo(() => errorLines(text, shownErrors), [text, shownErrors]);

  function edit(value: string) {
    setText(value);
    setSaveErrors([]);
    setSaveMessage(null);
  }

  async function save() {
    const rule = validation.rule;
    if (!rule) return;
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const { data, error } = await apiClient.PUT("/api/v1/rules/{rule_id}", {
        params: { path: { rule_id: source.id ?? rule.id } },
        body: { rule, actor: { id: `${team}-operator`, display_name: null } },
      });
      if (data) onSaved(data);
      else {
        setSaveErrors(detailsFromBody(error));
        setSaveMessage(messageFromBody(error, "The rule could not be saved. Check the fields."));
      }
    } catch (e) {
      setSaveMessage(e instanceof Error ? e.message : "API unreachable");
    } finally {
      setIsSaving(false);
    }
  }

  return {
    text,
    edit,
    validation,
    isChanged,
    isValid,
    shownErrors,
    lines,
    isSaving,
    saveMessage,
    save,
  };
}
