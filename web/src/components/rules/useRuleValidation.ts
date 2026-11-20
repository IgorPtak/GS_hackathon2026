import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { ConfigValidationError, Rule } from "../../api/types";

const DEBOUNCE_MS = 400;

interface Checked {
  readonly yaml: string;
  readonly errors: ConfigValidationError[];
  readonly rule: Rule | null;
  readonly requestError: string | null;
}

/** Debounced POST /config/validate; results are keyed by the YAML they were computed for. */
export function useRuleValidation(yaml: string) {
  const [checked, setChecked] = useState<Checked | null>(null);

  useEffect(() => {
    let isCancelled = false;
    const timer = setTimeout(() => {
      apiClient
        .POST("/api/v1/config/validate", { body: { kind: "rule", yaml } })
        .then(({ data, response }) => {
          if (isCancelled) return;
          if (!data) {
            setChecked({
              yaml,
              errors: [],
              rule: null,
              requestError: `Validation failed (API error ${String(response.status)})`,
            });
            return;
          }
          const isValid = data.is_valid && data.document !== null;
          setChecked({
            yaml,
            errors: data.errors ?? [],
            // The server validated the document against the Rule model.
            rule: isValid ? (data.document as unknown as Rule) : null,
            requestError: null,
          });
        })
        .catch((e: unknown) => {
          if (isCancelled) return;
          setChecked({
            yaml,
            errors: [],
            rule: null,
            requestError: e instanceof Error ? e.message : "API unreachable",
          });
        });
    }, DEBOUNCE_MS);
    return () => {
      isCancelled = true;
      clearTimeout(timer);
    };
  }, [yaml]);

  const isCurrent = checked?.yaml === yaml;
  return {
    isChecking: !isCurrent,
    errors: isCurrent ? checked.errors : [],
    rule: isCurrent ? checked.rule : null,
    requestError: isCurrent ? checked.requestError : null,
  };
}
