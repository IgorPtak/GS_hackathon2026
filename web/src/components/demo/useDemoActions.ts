import { useCallback, useEffect, useState } from "react";

import type { TabId } from "../../lib/tabs";
import { useToast } from "../ui/toastContext";
import {
  buildFreshRatesAlert,
  buildFreshSettlementsFailure,
  buildFreshUnknownSample,
} from "./fixtures";

export type DemoActionId = "rates" | "settlements" | "duplicates" | "sms_outage" | "unknown_schema";

const DUPLICATE_TOTAL = 500;
const DUPLICATE_CHUNK_SIZE = 100;

interface OutageResponse {
  readonly is_down?: boolean;
  readonly channels?: readonly string[];
}

async function postJson(url: string, body: unknown): Promise<Response> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Request returned ${String(response.status)}`);
  }
  return response;
}

function navigateToPath(path: string, onNavigate?: (tab: TabId) => void, tab?: TabId): void {
  if (onNavigate && tab) {
    onNavigate(tab);
    return;
  }
  const params = new URLSearchParams(window.location.search);
  params.delete("demo");
  const query = params.toString();
  const nextUrl = query ? `${path}?${query}` : path;
  window.history.pushState(null, "", nextUrl);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

/** Triggers live demo scenarios through /api/v1/ingest and /gateway/admin/outage. */
export function useDemoActions(options: {
  readonly onNavigate?: (tab: TabId) => void;
  readonly onAfterNavigate?: () => void;
}) {
  const { onNavigate, onAfterNavigate } = options;
  const toast = useToast();
  const [busyAction, setBusyAction] = useState<DemoActionId | null>(null);
  const [isSmsDown, setIsSmsDown] = useState(false);

  useEffect(() => {
    let isCancelled = false;
    fetch("/gateway/admin/outage")
      .then((res) => (res.ok ? (res.json() as Promise<OutageResponse>) : null))
      .then((data) => {
        if (isCancelled || !data) return;
        const channels = data.channels ?? [];
        setIsSmsDown(Boolean(data.is_down && (channels.length === 0 || channels.includes("sms"))));
      })
      .catch(() => {
        // Leave default state when the mock gateway proxy is unavailable.
      });
    return () => {
      isCancelled = true;
    };
  }, []);

  const runAction = useCallback(
    async (id: DemoActionId, task: () => Promise<string>) => {
      setBusyAction(id);
      try {
        const message = await task();
        toast.show(message, "success");
      } catch (e) {
        const reason = e instanceof Error ? e.message : "Request failed";
        toast.show(`Could not run scenario (${reason}).`, "error");
      } finally {
        setBusyAction(null);
      }
    },
    [toast],
  );

  const sendRatesAlert = useCallback(
    () =>
      runAction("rates", async () => {
        const { event, tradeId } = buildFreshRatesAlert();
        await postJson("/api/v1/ingest/rates-oms", event);
        return `Rates alert sent (${tradeId})`;
      }),
    [runAction],
  );

  const sendSettlementsFailure = useCallback(
    () =>
      runAction("settlements", async () => {
        const { event, workflowId } = buildFreshSettlementsFailure();
        await postJson("/api/v1/ingest/settlements-engine", event);
        return `Settlements failure sent (${workflowId})`;
      }),
    [runAction],
  );

  const sendDuplicates = useCallback(
    () =>
      runAction("duplicates", async () => {
        const { event } = buildFreshRatesAlert("DUP");
        let sent = 0;
        while (sent < DUPLICATE_TOTAL) {
          const size = Math.min(DUPLICATE_CHUNK_SIZE, DUPLICATE_TOTAL - sent);
          const chunk = Array.from({ length: size }, () => event);
          await postJson("/api/v1/ingest/rates-oms/batch", chunk);
          sent += size;
        }
        return "Sent 500 duplicates — folded into one alert";
      }),
    [runAction],
  );

  const toggleSmsGateway = useCallback(
    () =>
      runAction("sms_outage", async () => {
        const nextDown = !isSmsDown;
        const response = await postJson("/gateway/admin/outage", {
          is_down: nextDown,
          channels: ["sms"],
        });
        const data = (await response.json()) as OutageResponse;
        const down = Boolean(data.is_down && (data.channels ?? []).includes("sms"));
        setIsSmsDown(down);
        return down
          ? "SMS gateway is now down — deliveries will retry"
          : "SMS gateway is back up — queued messages will flush";
      }),
    [isSmsDown, runAction],
  );

  const sendUnknownSample = useCallback(
    () =>
      runAction("unknown_schema", async () => {
        const { event, sampleId } = buildFreshUnknownSample();
        await postJson("/api/v1/ingest/generic-webhook", event);
        onAfterNavigate?.();
        navigateToPath("/connect", onNavigate, "connect");
        return `Sent unknown sample (${sampleId}) — opening Connect a system`;
      }),
    [onAfterNavigate, onNavigate, runAction],
  );

  return {
    busyAction,
    isSmsDown,
    sendRatesAlert,
    sendSettlementsFailure,
    sendDuplicates,
    toggleSmsGateway,
    sendUnknownSample,
  };
}
