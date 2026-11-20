import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import { toYamlLines } from "./yamlLite";

interface Loaded {
  readonly ruleId: string;
  readonly lines: readonly string[] | null;
  readonly error: string | null;
}

const cache = new Map<string, readonly string[]>();

async function fetchLines(ruleId: string): Promise<readonly string[]> {
  const record = await apiClient.GET("/api/v1/rules/{rule_id}", {
    params: { path: { rule_id: ruleId } },
  });
  if (!record.data)
    throw new Error(`Cannot load rule (API error ${String(record.response.status)})`);
  const checked = await apiClient.POST("/api/v1/config/validate", {
    body: { kind: "rule", yaml: record.data.yaml },
  });
  if (!checked.data?.document) throw new Error("Cannot read the current rule");
  return toYamlLines(checked.data.document);
}

/** Current rule as serialized lines (server document run through the local serializer). */
export function useCurrentRuleLines(ruleId: string | null) {
  const [state, setState] = useState<Loaded | null>(null);
  useEffect(() => {
    if (ruleId === null || cache.has(ruleId)) return;
    let isCancelled = false;
    fetchLines(ruleId)
      .then((lines) => {
        cache.set(ruleId, lines);
        if (!isCancelled) setState({ ruleId, lines, error: null });
      })
      .catch((e: unknown) => {
        if (!isCancelled)
          setState({
            ruleId,
            lines: null,
            error: e instanceof Error ? e.message : "API unreachable",
          });
      });
    return () => {
      isCancelled = true;
    };
  }, [ruleId]);
  if (ruleId === null) return { lines: null, error: null };
  const cached = cache.get(ruleId);
  if (cached) return { lines: cached, error: null };
  const own = state?.ruleId === ruleId ? state : null;
  return { lines: own?.lines ?? null, error: own?.error ?? null };
}
