import { useEffect, useMemo, useState } from "react";

import { apiClient } from "../../api/client";
import type { ConfigValidationError, Rule } from "../../api/types";
import { ValidationErrorList } from "../rules/ValidationErrorList";
import { YamlEditor } from "../rules/YamlEditor";
import { errorLines } from "../rules/ruleErrors";
import { useRuleValidation } from "../rules/useRuleValidation";
import { Skeleton } from "../ui/Skeleton";

interface RuleYamlFieldProps {
  readonly ruleId: string;
  readonly serverErrors: readonly ConfigValidationError[];
  readonly onRuleChange: (rule: Rule | null) => void;
  /** Replaces the editor text (e.g. an AI draft); a new `nonce` re-applies it. */
  readonly prefill?: { readonly yaml: string; readonly nonce: number } | null;
}

function Editor({
  initial,
  serverErrors,
  onRuleChange,
}: Omit<RuleYamlFieldProps, "ruleId" | "prefill"> & { initial: string }) {
  const [text, setText] = useState(initial);
  const validation = useRuleValidation(text);
  const { rule } = validation;
  useEffect(() => {
    onRuleChange(rule);
  }, [rule, onRuleChange]);
  const shown = serverErrors.length > 0 ? serverErrors : validation.errors;
  const lines = useMemo(() => errorLines(text, shown), [text, shown]);

  return (
    <div className="space-y-2">
      <p className="text-meta font-medium text-ink">Proposed rule YAML</p>
      <div className="overflow-hidden rounded-input border border-hairline">
        <YamlEditor value={text} errorLines={lines} onChange={setText} />
      </div>
      <ValidationErrorList
        errors={shown}
        isChecking={validation.isChecking}
        isValid={rule !== null}
        requestError={validation.requestError}
      />
    </div>
  );
}

/** Loads the current rule YAML of the alert and edits it with live validation. */
export function RuleYamlField({
  ruleId,
  serverErrors,
  onRuleChange,
  prefill = null,
}: RuleYamlFieldProps) {
  const [loaded, setLoaded] = useState<{
    id: string;
    yaml: string | null;
    error: string | null;
  } | null>(null);

  useEffect(() => {
    let isCancelled = false;
    apiClient
      .GET("/api/v1/rules/{rule_id}", { params: { path: { rule_id: ruleId } } })
      .then(({ data, response }) => {
        if (isCancelled) return;
        setLoaded({
          id: ruleId,
          yaml: data?.yaml ?? null,
          error: data
            ? null
            : `Could not load rule ${ruleId} (API error ${String(response.status)}).`,
        });
      })
      .catch((e: unknown) => {
        if (!isCancelled) {
          setLoaded({
            id: ruleId,
            yaml: null,
            error: e instanceof Error ? e.message : "API unreachable",
          });
        }
      });
    return () => {
      isCancelled = true;
    };
  }, [ruleId]);

  if (loaded?.id !== ruleId) return <Skeleton className="h-48 w-full" />;
  if (loaded.yaml === null) {
    return (
      <p
        role="alert"
        className="rounded-tile border border-critical/30 bg-critical/8 px-3.5 py-2.5 text-meta text-critical-ink"
      >
        {loaded.error}
      </p>
    );
  }
  return (
    <Editor
      key={prefill?.nonce ?? 0}
      initial={prefill?.yaml ?? loaded.yaml}
      serverErrors={serverErrors}
      onRuleChange={onRuleChange}
    />
  );
}
