import { useEffect, useState } from "react";

import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Skeleton } from "../ui/Skeleton";
import { AlertListRow } from "./AlertListRow";
import type { AlertFeedApi } from "./useAlertFeed";
import { useFreshAlertIds } from "./useFreshAlertIds";

const CLOCK_TICK_MS = 30_000;

interface AlertListProps {
  readonly feed: AlertFeedApi;
  readonly selectedAlertId: string | null;
  readonly onSelect: (alertId: string) => void;
}

/** Live list of alerts for the picked team and filter, with cursor paging. */
export function AlertList({ feed, selectedAlertId, onSelect }: AlertListProps) {
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
  const freshIds = useFreshAlertIds(feed.items, feed.isLoading);

  return (
    <Card isPadded={false} className="overflow-hidden">
      {feed.error ? (
        <p
          role="alert"
          className="m-2 rounded-input bg-warning/20 px-3 py-2 text-meta text-warning-ink"
        >
          Cannot load alerts ({feed.error}).{" "}
          <button type="button" className="font-medium underline" onClick={feed.reload}>
            Try again
          </button>
        </p>
      ) : null}
      {feed.isLoading && !feed.error ? (
        <div className="flex flex-col gap-3 p-3" aria-busy="true">
          {[0, 1, 2].map((key) => (
            <Skeleton key={key} className="h-16" />
          ))}
        </div>
      ) : feed.items.length === 0 ? (
        feed.error ? null : (
          <p className="px-4 py-8 text-center text-body text-ink-2">No alerts in this view.</p>
        )
      ) : (
        <ul className="flex flex-col divide-y divide-hairline">
          {feed.items.map((alert) => (
            <AlertListRow
              key={alert.id}
              alert={alert}
              isSelected={alert.id === selectedAlertId}
              isFresh={freshIds.has(alert.id)}
              now={now}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
      {feed.nextCursor !== null ? (
        <div className="p-2">
          <Button isLoading={feed.isLoadingMore} onClick={feed.loadMore} className="w-full">
            Load more
          </Button>
        </div>
      ) : null}
    </Card>
  );
}
