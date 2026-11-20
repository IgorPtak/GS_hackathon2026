import { useEffect, useState } from "react";

import type { StreamStatus } from "../../hooks/useEventStream";
import type { AlertFeedApi, StatusFilter } from "./useAlertFeed";
import { AlertRow } from "./AlertRow";
import { ConnectionIndicator } from "./ConnectionIndicator";

const FILTERS: readonly { readonly id: StatusFilter; readonly label: string }[] = [
  { id: "open", label: "Open" },
  { id: "acknowledged", label: "Acknowledged" },
  { id: "resolved", label: "Resolved" },
  { id: "all", label: "All" },
];

const CLOCK_TICK_MS = 30_000;

interface AlertFeedProps {
  feed: AlertFeedApi;
  filter: StatusFilter;
  streamStatus: StreamStatus;
  selectedAlertId: string | null;
  onFilterChange: (filter: StatusFilter) => void;
  onSelect: (alertId: string) => void;
}

/** Live list of alerts for the picked team with a status filter and cursor paging. */
export function AlertFeed({
  feed,
  filter,
  streamStatus,
  selectedAlertId,
  onFilterChange,
  onSelect,
}: AlertFeedProps) {
  // Re-render periodically so relative times ("2 min ago") do not go stale.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => {
      setNow(Date.now());
    }, CLOCK_TICK_MS);
    return () => {
      window.clearInterval(timer);
    };
  }, []);

  return (
    <section className="rounded border border-slate-200 bg-white p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Alerts</h2>
        <div className="flex flex-wrap items-center gap-3">
          <ConnectionIndicator status={streamStatus} />
          <label className="flex items-center gap-2 text-sm">
            <span className="text-slate-600">Status</span>
            <select
              value={filter}
              onChange={(e) => {
                onFilterChange(e.target.value as StatusFilter);
              }}
              className="rounded border border-slate-300 px-2 py-1 text-sm"
            >
              {FILTERS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {feed.error ? (
        <p role="alert" className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Cannot load alerts ({feed.error}).{" "}
          <button type="button" className="underline" onClick={feed.reload}>
            Retry
          </button>
        </p>
      ) : null}

      {feed.isLoading ? (
        feed.error ? null : (
          <p className="mt-3 text-sm text-slate-500">Loading alerts...</p>
        )
      ) : feed.items.length === 0 ? (
        feed.error ? null : (
          <p className="mt-3 text-sm text-slate-500">No alerts yet</p>
        )
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {feed.items.map((alert) => (
            <AlertRow
              key={alert.id}
              alert={alert}
              isSelected={alert.id === selectedAlertId}
              now={now}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}

      {feed.nextCursor !== null ? (
        <button
          type="button"
          disabled={feed.isLoadingMore}
          onClick={feed.loadMore}
          className="mt-3 rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          {feed.isLoadingMore ? "Loading..." : "Load more"}
        </button>
      ) : null}
    </section>
  );
}
