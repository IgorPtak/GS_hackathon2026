import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { Runbook, RunbookSummary } from "../../api/types";

interface Loaded<T> {
  readonly key: string;
  readonly data: T | null;
  readonly error: string | null;
}

async function fetchList(): Promise<Loaded<RunbookSummary[]>> {
  try {
    const { data, response } = await apiClient.GET("/api/v1/runbooks");
    return data
      ? { key: "", data, error: null }
      : { key: "", data: null, error: `API error ${String(response.status)}` };
  } catch (e) {
    return { key: "", data: null, error: e instanceof Error ? e.message : "API unreachable" };
  }
}

async function fetchOne(id: string): Promise<Loaded<Runbook>> {
  try {
    const { data, response } = await apiClient.GET("/api/v1/runbooks/{runbook_id}", {
      params: { path: { runbook_id: id } },
    });
    return data
      ? { key: id, data, error: null }
      : { key: id, data: null, error: `API error ${String(response.status)}` };
  } catch (e) {
    return { key: id, data: null, error: e instanceof Error ? e.message : "API unreachable" };
  }
}

/** Runbook summaries plus the full runbook of the selected id. */
export function useRunbooks(selectedId: string | null) {
  const [list, setList] = useState<Loaded<RunbookSummary[]> | null>(null);
  const [one, setOne] = useState<Loaded<Runbook> | null>(null);

  useEffect(() => {
    let isCancelled = false;
    void fetchList().then((result) => {
      if (!isCancelled) setList(result);
    });
    return () => {
      isCancelled = true;
    };
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    let isCancelled = false;
    void fetchOne(selectedId).then((result) => {
      if (!isCancelled) setOne(result);
    });
    return () => {
      isCancelled = true;
    };
  }, [selectedId]);

  const isOneCurrent = selectedId !== null && one?.key === selectedId;
  return {
    summaries: list?.data ?? [],
    isListLoading: list === null,
    listError: list?.error ?? null,
    runbook: isOneCurrent ? one.data : null,
    isRunbookLoading: selectedId !== null && !isOneCurrent,
    runbookError: isOneCurrent ? one.error : null,
  };
}
