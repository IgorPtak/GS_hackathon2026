import { useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { EventEnvelope } from "../../api/types";
import { cx } from "../../lib/cx";

const POLL_MS = 1500;
const LIMIT = 40;

/** One line of the most telling payload values, so a row reads without opening the JSON. */
function summarize(payload: Record<string, unknown>): string {
  const parts: string[] = [];
  const visit = (value: unknown, depth: number) => {
    if (parts.length >= 5 || value === null || value === undefined) return;
    if (typeof value === "object" && !Array.isArray(value) && depth < 2) {
      for (const child of Object.values(value as Record<string, unknown>)) visit(child, depth + 1);
    } else if (typeof value === "string" || typeof value === "number") {
      parts.push(String(value));
    }
  };
  visit(payload, 0);
  return parts.join(" · ");
}

/** Raw events as ingest received them, newest first; new rows slide in while you watch. */
export function LiveEventStream({ isActive }: { readonly isActive: boolean }) {
  const [events, setEvents] = useState<readonly EventEnvelope[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const seen = useRef<Set<string> | null>(null);
  const [freshIds, setFreshIds] = useState<ReadonlySet<string>>(new Set());

  useEffect(() => {
    if (!isActive) return;
    let isCancelled = false;
    const load = async () => {
      try {
        const { data } = await apiClient.GET("/api/v1/events/recent", {
          params: { query: { limit: LIMIT } },
        });
        if (isCancelled || !data) return;
        const known = seen.current;
        const fresh = new Set(
          known ? data.filter((e) => !known.has(e.event_id)).map((e) => e.event_id) : [],
        );
        seen.current = new Set(data.map((e) => e.event_id));
        setFreshIds(fresh);
        setEvents(data);
        setError(null);
      } catch {
        if (!isCancelled) setError("Cannot reach the API");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => {
      isCancelled = true;
      window.clearInterval(timer);
    };
  }, [isActive]);

  if (error) {
    return <p className="px-4 py-6 text-meta text-warning-ink">{error}. Retrying…</p>;
  }
  if (events === null) {
    return <p className="px-4 py-6 text-meta text-ink-3">Listening…</p>;
  }
  if (events.length === 0) {
    return <p className="px-4 py-6 text-meta text-ink-3">No events yet. Run a scenario.</p>;
  }
  return (
    <ul className="flex flex-col font-mono text-caption">
      {events.map((event) => {
        const isOpen = openId === event.event_id;
        return (
          <li
            key={event.event_id}
            className={cx(
              "border-b border-hairline/70 last:border-0",
              freshIds.has(event.event_id) && "animate-row-in",
            )}
          >
            <button
              type="button"
              aria-expanded={isOpen}
              onClick={() => {
                setOpenId(isOpen ? null : event.event_id);
              }}
              className="flex w-full items-baseline gap-3 px-4 py-2 text-left transition-colors hover:bg-fill/60"
            >
              <span className="num shrink-0 text-ink-3">
                {new Date(event.received_at).toLocaleTimeString([], { hour12: false })}
              </span>
              <span className="shrink-0 font-semibold text-accent-ink">{event.source_id}</span>
              <span className="truncate text-ink-2">{summarize(event.payload)}</span>
            </button>
            {isOpen ? (
              <pre className="mx-4 mb-3 max-h-56 animate-fade-in overflow-auto rounded-input bg-fill p-3 text-ink">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
