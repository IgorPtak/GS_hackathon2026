import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { EventEnvelope } from "../../api/types";
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
    <section className="rounded border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Recent events</h2>
        <label className="flex items-center gap-2 text-sm">
          <span className="text-slate-600">Source ID</span>
          <input
            type="text"
            value={sourceId}
            onChange={(e) => {
              setSourceId(e.target.value);
            }}
            placeholder="All sources"
            className="w-48 rounded border border-slate-300 px-2 py-1 text-sm"
          />
        </label>
      </div>
      {error ? (
        <p role="alert" className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Cannot load events ({error}). Retrying every 2 s.
        </p>
      ) : null}
      {events === null ? (
        error ? null : (
          <p className="mt-3 text-sm text-slate-500">Loading events...</p>
        )
      ) : events.length === 0 ? (
        <p className="mt-3 text-sm text-slate-500">No events yet</p>
      ) : (
        <ul className="mt-3 divide-y divide-slate-100">
          {events.map((event) => (
            <li key={event.event_id} className="py-2 text-sm">
              <div className="flex flex-wrap gap-x-4 gap-y-1">
                <span className="font-medium">{event.source_id}</span>
                <span className="rounded bg-slate-100 px-1.5 text-xs leading-5">
                  {event.source_type}
                </span>
                <span className="text-slate-600">
                  {new Date(event.received_at).toLocaleString()}
                </span>
                <span className="break-all font-mono text-xs text-slate-500">{event.event_id}</span>
              </div>
              <EventJsonView payload={event.payload} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
