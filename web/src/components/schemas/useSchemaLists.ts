import { useCallback, useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { SchemaProfileRecord, UnknownSchemaSample } from "../../api/types";

interface Loaded<T> {
  readonly nonce: number;
  readonly items: T[];
  readonly error: string | null;
}

interface ListState<T> {
  readonly items: T[];
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly reload: () => void;
}

interface Result<T> {
  readonly data: T[] | undefined;
  readonly status: number;
}

function useList<T>(load: () => Promise<Result<T>>): ListState<T> {
  const [nonce, setNonce] = useState(0);
  const [loaded, setLoaded] = useState<Loaded<T> | null>(null);

  useEffect(() => {
    let isCancelled = false;
    load()
      .then(({ data, status }) => {
        if (isCancelled) return;
        setLoaded({ nonce, items: data ?? [], error: data ? null : `API error ${String(status)}` });
      })
      .catch((e: unknown) => {
        if (isCancelled) return;
        setLoaded({
          nonce,
          items: [],
          error: e instanceof Error ? e.message : "API unreachable",
        });
      });
    return () => {
      isCancelled = true;
    };
  }, [load, nonce]);

  const reload = useCallback(() => {
    setNonce((n) => n + 1);
  }, []);
  return {
    items: loaded?.items ?? [],
    isLoading: loaded === null,
    error: loaded?.error ?? null,
    reload,
  };
}

async function loadUnknownSchemas(): Promise<Result<UnknownSchemaSample>> {
  const { data, response } = await apiClient.GET("/api/v1/unknown-schemas");
  return { data, status: response.status };
}

async function loadSchemaProfiles(): Promise<Result<SchemaProfileRecord>> {
  const { data, response } = await apiClient.GET("/api/v1/schema-profiles");
  return { data, status: response.status };
}

export function useUnknownSchemas(): ListState<UnknownSchemaSample> {
  return useList(loadUnknownSchemas);
}

export function useSchemaProfiles(): ListState<SchemaProfileRecord> {
  return useList(loadSchemaProfiles);
}
