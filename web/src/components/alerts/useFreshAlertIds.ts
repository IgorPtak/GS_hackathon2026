import { useState } from "react";

import type { Alert } from "../../api/types";

interface FreshState {
  readonly known: ReadonlySet<string>;
  readonly fresh: ReadonlySet<string>;
  readonly isReady: boolean;
}

function nextState(prev: FreshState, ids: readonly string[]): FreshState {
  if (!prev.isReady) return { known: new Set(ids), fresh: new Set(), isReady: true };
  const added = ids.filter((id) => !prev.known.has(id));
  if (added.length === 0) return prev;
  return {
    known: new Set([...prev.known, ...added]),
    fresh: new Set([...prev.fresh, ...added]),
    isReady: true,
  };
}

/** Ids that arrived after the first load; those rows get the slide-in animation. */
export function useFreshAlertIds(items: readonly Alert[], isLoading: boolean): ReadonlySet<string> {
  const [state, setState] = useState<FreshState>({
    known: new Set(),
    fresh: new Set(),
    isReady: false,
  });
  // Derived during render (React's "adjust state on prop change" pattern), so a new row is
  // already marked fresh on its first paint.
  if (!isLoading) {
    const next = nextState(
      state,
      items.map((item) => item.id),
    );
    if (next !== state) setState(next);
  }
  return state.fresh;
}
