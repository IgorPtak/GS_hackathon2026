import { useEffect, useRef, useState } from "react";

/** How long a decided card stays to show its outcome, then how long it takes to fold away. */
export const SHOW_OUTCOME_MS = 1300;
export const FOLD_MS = 450;

export type Outcome = "approve" | "reject";

interface Identified {
  readonly id: string;
}

export interface Shown<T extends Identified> {
  readonly item: T;
  /** Set once the item has left the pending list. */
  readonly outcome: Outcome | null;
  readonly isFolding: boolean;
}

interface Leaving<T extends Identified> {
  readonly item: T;
  readonly index: number;
  readonly outcome: Outcome;
  readonly isFolding: boolean;
}

/**
 * Keeps an item on screen briefly after it leaves a pending list (decided here, by phone or by a
 * teammate), so people see "Approved" before it folds away instead of it vanishing. Used for
 * runbook requests and fix proposals.
 */
export function useLingeringItems<T extends Identified>(
  items: readonly T[],
  outcomeOf: (id: string) => Outcome,
): readonly Shown<T>[] {
  const previous = useRef<readonly T[]>(items);
  const outcomeRef = useRef(outcomeOf);
  useEffect(() => {
    outcomeRef.current = outcomeOf;
  });
  const [leaving, setLeaving] = useState<ReadonlyMap<string, Leaving<T>>>(new Map());

  useEffect(() => {
    const current = new Set(items.map((item) => item.id));
    const gone = previous.current
      .map((item, index) => ({ item, index }))
      .filter(({ item }) => !current.has(item.id));
    previous.current = items;
    if (gone.length === 0) return;
    setLeaving((map) => {
      const next = new Map(map);
      for (const { item, index } of gone) {
        next.set(item.id, {
          item,
          index,
          outcome: outcomeRef.current(item.id),
          isFolding: false,
        });
      }
      return next;
    });
    for (const { item } of gone) {
      window.setTimeout(() => {
        setLeaving((map) => {
          const entry = map.get(item.id);
          if (!entry) return map;
          const next = new Map(map);
          next.set(item.id, { ...entry, isFolding: true });
          return next;
        });
      }, SHOW_OUTCOME_MS);
      window.setTimeout(() => {
        setLeaving((map) => {
          const next = new Map(map);
          next.delete(item.id);
          return next;
        });
      }, SHOW_OUTCOME_MS + FOLD_MS);
    }
  }, [items]);

  const shown: Shown<T>[] = items.map((item) => ({
    item,
    outcome: null,
    isFolding: false,
  }));
  const sorted = [...leaving.values()].sort((a, b) => a.index - b.index);
  for (const entry of sorted) {
    if (shown.some((visible) => visible.item.id === entry.item.id)) continue;
    shown.splice(Math.min(entry.index, shown.length), 0, {
      item: entry.item,
      outcome: entry.outcome,
      isFolding: entry.isFolding,
    });
  }
  return shown;
}
