import { useEffect, useRef, useState } from "react";

import type { ApprovalRequest } from "../../api/types";

/** How long a decided card stays to show its outcome, then how long it takes to fold away. */
export const SHOW_OUTCOME_MS = 1300;
export const FOLD_MS = 450;

export type Outcome = "approve" | "reject";

export interface ShownRequest {
  readonly request: ApprovalRequest;
  /** Set once the request has left the pending list. */
  readonly outcome: Outcome | null;
  readonly isFolding: boolean;
}

interface Leaving {
  readonly request: ApprovalRequest;
  readonly index: number;
  readonly outcome: Outcome;
  readonly isFolding: boolean;
}

/**
 * Keeps a request on screen briefly after it leaves the pending list (decided here, by phone or
 * by a teammate), so people see "Approved" before it folds away instead of it vanishing.
 */
export function useLingeringRequests(
  items: readonly ApprovalRequest[],
  outcomeOf: (id: string) => Outcome,
): readonly ShownRequest[] {
  const previous = useRef<readonly ApprovalRequest[]>(items);
  const outcomeRef = useRef(outcomeOf);
  useEffect(() => {
    outcomeRef.current = outcomeOf;
  });
  const [leaving, setLeaving] = useState<ReadonlyMap<string, Leaving>>(new Map());

  useEffect(() => {
    const current = new Set(items.map((item) => item.id));
    const gone = previous.current
      .map((request, index) => ({ request, index }))
      .filter(({ request }) => !current.has(request.id));
    previous.current = items;
    if (gone.length === 0) return;
    setLeaving((map) => {
      const next = new Map(map);
      for (const { request, index } of gone) {
        next.set(request.id, {
          request,
          index,
          outcome: outcomeRef.current(request.id),
          isFolding: false,
        });
      }
      return next;
    });
    for (const { request } of gone) {
      window.setTimeout(() => {
        setLeaving((map) => {
          const entry = map.get(request.id);
          if (!entry) return map;
          const next = new Map(map);
          next.set(request.id, { ...entry, isFolding: true });
          return next;
        });
      }, SHOW_OUTCOME_MS);
      window.setTimeout(() => {
        setLeaving((map) => {
          const next = new Map(map);
          next.delete(request.id);
          return next;
        });
      }, SHOW_OUTCOME_MS + FOLD_MS);
    }
  }, [items]);

  const shown: ShownRequest[] = items.map((request) => ({
    request,
    outcome: null,
    isFolding: false,
  }));
  const sorted = [...leaving.values()].sort((a, b) => a.index - b.index);
  for (const entry of sorted) {
    if (shown.some((item) => item.request.id === entry.request.id)) continue;
    shown.splice(Math.min(entry.index, shown.length), 0, {
      request: entry.request,
      outcome: entry.outcome,
      isFolding: entry.isFolding,
    });
  }
  return shown;
}
