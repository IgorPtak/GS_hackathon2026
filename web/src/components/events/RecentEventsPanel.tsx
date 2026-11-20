import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { EventEnvelope } from "../../api/types";
import { StatusChip } from "../ui/StatusChip";
import { EventJsonView } from "./EventJsonView";

const POLL_INTERVAL_MS = 2000;
const EVENT_LIMIT = 50;

export function RecentEventsPanel() {
  const [events, setEvents] = useState<readonly EventEnvelope[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sourceId, setSourceId] = useState("");
  const requestSeq = useRef(0);
  const invalidate = useCallback(() => {
    requestSeq.current += 1;
  }, []);

  const load = useCallback(async () => {
    const seq = ++requestSeq.current;
    try {
      const trimmed = sourceId.trim();
      const { data, error: apiError } = await apiClient.GET("/api/v1/events/recent", {
        params: { query: { limit: EVENT_LIMIT, ...(trimmed ? { source_id: trimmed } : {}) } },
      });
      if (seq !== requestSeq.current) return;
      if (data) {
        setEvents(data);
        setError(null);
      } else {
        setError(`API error: ${JSON.stringify(apiError)}`);
      }
    } catch (e) {
      if (seq !== requestSeq.current) return;
      setError(e instanceof Error ? e.message : "API unreachable");
    }
  }, [sourceId]);

  useEffect(() => {
    let timer: number | undefined;
    const stop = () => {
      if (timer !== undefined) {
        window.clearInterval(timer);
        timer = undefined;
      }
    };
    const start = () => {
      stop();
      void load();
      timer = window.setInterval(() => void load(), POLL_INTERVAL_MS);
    };
    const onVisibility = () => {
      if (document.visibilityState === "visible") start();
      else stop();
    };
    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
      invalidate();
    };
  }, [load, invalidate]);

  return (
    <div>
      <label className="flex flex-wrap items-center gap-2 text-meta">
        <span className="text-ink-2">Source</span>
        <input
          type="text"
          value={sourceId}
          onChange={(e) => {
            setSourceId(e.target.value);
          }}
          placeholder="All sources"
          className="h-9 w-48 rounded-input border border-hairline bg-fill px-3 text-body text-ink placeholder:text-ink-3"
        />
      </label>
      {error ? (
        <p
          role="alert"
          className="mt-3 rounded-input bg-warning/20 px-3 py-2 text-meta text-warning-ink"
        >
          Cannot load events ({error}). Trying again every 2 s.
        </p>
      ) : null}
      {events === null ? (
        error ? null : (
          <p className="mt-3 text-meta text-ink-2">Loading events...</p>
        )
      ) : events.length === 0 ? (
        <p className="mt-3 text-meta text-ink-2">No events yet.</p>
      ) : (
        <ul className="mt-3 divide-y divide-hairline">
          {events.map((event) => (
            <li key={event.event_id} className="py-2.5 text-body">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-medium">{event.source_id}</span>
                <StatusChip>{event.source_type}</StatusChip>
                <span className="num text-meta text-ink-2">
                  {new Date(event.received_at).toLocaleTimeString()}
                </span>
              </div>
              <EventJsonView payload={event.payload} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
