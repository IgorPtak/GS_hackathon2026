import { useEffect, useRef, useState } from "react";

import type { SseEvent } from "../api/types";

export type StreamStatus = "idle" | "connecting" | "open" | "retrying";

type SseEventType = SseEvent["type"];

/** One optional handler per event type; the payload type follows the `type` key. */
export type SseHandlers = {
  [T in SseEventType]?: (event: Extract<SseEvent, { type: T }>) => void;
} & {
  /** Called after the stream re-opens following a drop, so lists can refetch what they missed. */
  onReconnect?: () => void;
};

const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30_000;

/** The server sends `event: <type>`, so each type needs its own listener (onmessage would miss them). */
const EVENT_TYPES: Record<SseEventType, true> = {
  "alert.created": true,
  "alert.updated": true,
  notification: true,
  "delivery.updated": true,
  "phone.message": true,
  "action_run.updated": true,
  "approval.requested": true,
  "approval.decided": true,
  "fix_proposal.updated": true,
  "unknown_schema.detected": true,
  "audit.appended": true,
  "config.changed": true,
};

function isSseEvent(value: unknown): value is SseEvent {
  if (typeof value !== "object" || value === null || !("type" in value)) return false;
  return typeof value.type === "string" && value.type in EVENT_TYPES;
}

function dispatch(handlers: SseHandlers, event: SseEvent): void {
  // The cast is needed because TypeScript cannot correlate the handler key with the narrowed event.
  const handler = handlers[event.type] as ((e: SseEvent) => void) | undefined;
  handler?.(event);
}

interface StatusState {
  readonly team: string | null;
  readonly status: StreamStatus;
}

/**
 * Subscribes to `/api/v1/stream?team=` and dispatches parsed `SseEvent`s by `type`.
 * Reconnects with exponential backoff (1 s up to 30 s); closes on unmount or team change.
 */
export function useEventStream(team: string | null, handlers: SseHandlers): StreamStatus {
  const [state, setState] = useState<StatusState>({ team, status: "connecting" });
  const handlersRef = useRef(handlers);

  useEffect(() => {
    handlersRef.current = handlers;
  });

  useEffect(() => {
    if (team === null) return;
    let source: EventSource | null = null;
    let timer: number | undefined;
    let backoff = INITIAL_BACKOFF_MS;
    let hasDropped = false;
    let isClosed = false;

    const connect = () => {
      const next = new EventSource(`/api/v1/stream?team=${encodeURIComponent(team)}`);
      source = next;
      next.onopen = () => {
        backoff = INITIAL_BACKOFF_MS;
        setState({ team, status: "open" });
        if (hasDropped) {
          hasDropped = false;
          handlersRef.current.onReconnect?.();
        }
      };
      next.onerror = () => {
        // Close ourselves: the browser gives up silently on HTTP errors, and we want our backoff.
        next.close();
        if (isClosed) return;
        hasDropped = true;
        setState({ team, status: "retrying" });
        timer = window.setTimeout(connect, backoff);
        backoff = Math.min(backoff * 2, MAX_BACKOFF_MS);
      };
      for (const type of Object.keys(EVENT_TYPES)) {
        next.addEventListener(type, (message) => {
          if (!(message instanceof MessageEvent) || typeof message.data !== "string") return;
          try {
            const parsed: unknown = JSON.parse(message.data);
            if (isSseEvent(parsed)) dispatch(handlersRef.current, parsed);
          } catch {
            // A malformed frame must not kill the stream.
          }
        });
      }
    };

    connect();
    return () => {
      isClosed = true;
      window.clearTimeout(timer);
      source?.close();
    };
  }, [team]);

  if (team === null) return "idle";
  return state.team === team ? state.status : "connecting";
}
