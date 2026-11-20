import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { Alert, AlertPage, AlertStatus } from "../../api/types";
import { upsertAlert } from "./alertFormat";

type PageResult = { readonly data: AlertPage } | { readonly failure: string };

export type StatusFilter = AlertStatus | "all";

const PAGE_SIZE = 50;

interface FeedState {
  /** Which team + filter the data belongs to; a mismatch with the current key means "loading". */
  readonly key: string;
  readonly items: readonly Alert[];
  readonly nextCursor: string | null;
  readonly error: string | null;
}

function describeFailure(status: number | undefined, error: unknown): string {
  if (status !== undefined) return `API error ${String(status)}`;
  return error instanceof Error ? error.message : "API unreachable";
}

function isVisible(alert: Alert, team: string, filter: StatusFilter): boolean {
  return alert.team === team && (filter === "all" || alert.status === filter);
}

export interface AlertFeedApi {
  readonly items: readonly Alert[];
  readonly nextCursor: string | null;
  readonly isLoading: boolean;
  readonly isLoadingMore: boolean;
  readonly error: string | null;
  /** Merge an alert from SSE or an action response. */
  readonly applyAlert: (alert: Alert, isForced?: boolean) => void;
  readonly loadMore: () => void;
  readonly reload: () => void;
}

/** Alert list for one team and status filter: paged fetch plus merge of live updates. */
export function useAlertFeed(team: string, filter: StatusFilter): AlertFeedApi {
  const key = `${team}|${filter}`;
  const [state, setState] = useState<FeedState>({ key, items: [], nextCursor: null, error: null });
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const keyRef = useRef(key);

  const fetchPage = useCallback(
    async (cursor: string | null): Promise<PageResult> => {
      const { data, error, response } = await apiClient.GET("/api/v1/alerts", {
        params: {
          query: {
            team,
            limit: PAGE_SIZE,
            ...(filter === "all" ? {} : { status: filter }),
            ...(cursor ? { cursor } : {}),
          },
        },
      });
      return data ? { data } : { failure: describeFailure(response.status, error) };
    },
    [team, filter],
  );

  /** `isReplace` drops the old list (new team/filter); otherwise the page is merged into it. */
  const load = useCallback(
    async (isReplace: boolean) => {
      let result: PageResult;
      try {
        result = await fetchPage(null);
      } catch (e) {
        result = { failure: describeFailure(undefined, e) };
      }
      if (keyRef.current !== key) return;
      setState((prev) => {
        if ("failure" in result) {
          return { ...prev, key, error: result.failure, items: prev.key === key ? prev.items : [] };
        }
        const base = isReplace || prev.key !== key ? [] : prev.items;
        const merged = result.data.items.reduce<readonly Alert[]>(
          (list, alert) => upsertAlert(list, alert),
          base.filter((alert) => isVisible(alert, team, filter)),
        );
        const cursor = isReplace || prev.key !== key ? result.data.next_cursor : prev.nextCursor;
        return { key, items: merged, nextCursor: cursor, error: null };
      });
    },
    [fetchPage, key, team, filter],
  );

  useEffect(() => {
    keyRef.current = key;
    void load(true);
  }, [key, load]);

  const reload = useCallback(() => {
    void load(false);
  }, [load]);

  const loadMore = useCallback(() => {
    if (state.nextCursor === null || state.key !== key) return;
    setIsLoadingMore(true);
    void fetchPage(state.nextCursor)
      .then((result) => {
        if (keyRef.current !== key) return;
        setState((prev) => {
          if ("failure" in result) return { ...prev, error: result.failure };
          const items = result.data.items.reduce<readonly Alert[]>(
            (list, alert) => upsertAlert(list, alert),
            prev.items,
          );
          return { ...prev, items, nextCursor: result.data.next_cursor, error: null };
        });
      })
      .catch((e: unknown) => {
        setState((prev) => ({ ...prev, error: describeFailure(undefined, e) }));
      })
      .finally(() => {
        setIsLoadingMore(false);
      });
  }, [fetchPage, key, state.key, state.nextCursor]);

  const applyAlert = useCallback(
    (alert: Alert, isForced = false) => {
      setState((prev) => {
        const existing = prev.items.find((item) => item.id === alert.id);
        if (
          existing &&
          !isForced &&
          Date.parse(alert.updated_at) < Date.parse(existing.updated_at)
        ) {
          return prev;
        }
        if (!isVisible(alert, team, filter)) {
          return { ...prev, items: prev.items.filter((item) => item.id !== alert.id) };
        }
        return { ...prev, items: upsertAlert(prev.items, alert, isForced) };
      });
    },
    [team, filter],
  );

  const isCurrent = state.key === key;
  return {
    items: isCurrent ? state.items : [],
    nextCursor: isCurrent ? state.nextCursor : null,
    isLoading: !isCurrent,
    isLoadingMore,
    error: isCurrent ? state.error : null,
    applyAlert,
    loadMore,
    reload,
  };
}
