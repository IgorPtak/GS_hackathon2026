import { useCallback, useState } from "react";

import { apiClient } from "../../api/client";
import type { Runbook } from "../../api/types";
import { messageFromBody } from "../rules/ruleErrors";
import type { RunbookFormatId } from "./runbookFormat";

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : "API unreachable";
}

/** Normalize a pasted runbook for review, then save it (the server normalizes again on save). */
export function useAddRunbook(team: string | null) {
  const [preview, setPreview] = useState<Runbook | null>(null);
  const [isReading, setIsReading] = useState(false);
  const [readError, setReadError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const read = useCallback(async (format: RunbookFormatId, source: string) => {
    setIsReading(true);
    setReadError(null);
    setPreview(null);
    try {
      const { data, error } = await apiClient.POST("/api/v1/runbooks/normalize", {
        body: { format, source },
      });
      if (data) setPreview(data);
      else setReadError(messageFromBody(error, "Beacon could not read this runbook."));
    } catch (e) {
      setReadError(errorText(e));
    } finally {
      setIsReading(false);
    }
  }, []);

  const save = useCallback(
    async (id: string, title: string): Promise<Runbook | null> => {
      if (!preview) return null;
      setIsSaving(true);
      setSaveError(null);
      try {
        const { data, error } = await apiClient.PUT("/api/v1/runbooks/{runbook_id}", {
          params: { path: { runbook_id: id } },
          body: {
            id,
            title,
            team,
            format: preview.format,
            source: preview.source,
            actor: { id: `${team ?? "team"}-operator`, display_name: null },
          },
        });
        if (data) return data;
        setSaveError(messageFromBody(error, "Beacon could not save this runbook."));
        return null;
      } catch (e) {
        setSaveError(errorText(e));
        return null;
      } finally {
        setIsSaving(false);
      }
    },
    [preview, team],
  );

  const reset = useCallback(() => {
    setPreview(null);
    setReadError(null);
    setSaveError(null);
  }, []);

  return { preview, isReading, readError, isSaving, saveError, read, save, reset };
}
