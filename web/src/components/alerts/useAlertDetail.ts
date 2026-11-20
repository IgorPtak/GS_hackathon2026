import { useCallback, useEffect, useRef, useState } from "react";

import { apiClient } from "../../api/client";
import type { Alert, AlertDetail, AuditEntry, Delivery } from "../../api/types";

interface DetailState {
  readonly alertId: string | null;
  readonly detail: AlertDetail | null;
  readonly error: string | null;
}

export interface AlertDetailApi {
  readonly detail: AlertDetail | null;
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly applyAlert: (alert: Alert, isForced?: boolean) => void;
  readonly applyAudit: (entry: AuditEntry) => void;
  readonly applyDelivery: (delivery: Delivery) => void;
  readonly reload: () => void;
}

function byAuditOrder(a: AuditEntry, b: AuditEntry): number {
  return Date.parse(a.at) - Date.parse(b.at) || a.id - b.id;
}

/** Detail of the selected alert; live audit entries, deliveries and alert updates merge into it. */
export function useAlertDetail(alertId: string | null): AlertDetailApi {
  const [state, setState] = useState<DetailState>({ alertId, detail: null, error: null });
  const idRef = useRef(alertId);

  const load = useCallback(async () => {
    if (alertId === null) return;
    let next: DetailState;
    try {
      const { data, error, response } = await apiClient.GET("/api/v1/alerts/{alert_id}", {
        params: { path: { alert_id: alertId } },
      });
      next = data
        ? { alertId, detail: data, error: null }
        : {
            alertId,
            detail: null,
            error: `API error ${String(response.status)}: ${JSON.stringify(error)}`,
          };
    } catch (e) {
      next = { alertId, detail: null, error: e instanceof Error ? e.message : "API unreachable" };
    }
    if (idRef.current !== alertId) return;
    // A failed refetch must not blank a detail we already show.
    setState((prev) =>
      next.detail || prev.alertId !== alertId ? next : { ...prev, error: next.error },
    );
  }, [alertId]);

  useEffect(() => {
    idRef.current = alertId;
    void load();
  }, [alertId, load]);

  const update = useCallback((id: string, change: (detail: AlertDetail) => AlertDetail) => {
    setState((prev) =>
      prev.alertId === id && prev.detail ? { ...prev, detail: change(prev.detail) } : prev,
    );
  }, []);

  const applyAlert = useCallback(
    (alert: Alert, isForced = false) => {
      update(alert.id, (detail) =>
        !isForced && Date.parse(alert.updated_at) < Date.parse(detail.alert.updated_at)
          ? detail
          : { ...detail, alert },
      );
    },
    [update],
  );

  const applyAudit = useCallback(
    (entry: AuditEntry) => {
      update(entry.alert_id, (detail) =>
        detail.audit_entries.some((existing) => existing.id === entry.id)
          ? detail
          : { ...detail, audit_entries: [...detail.audit_entries, entry].sort(byAuditOrder) },
      );
    },
    [update],
  );

  const applyDelivery = useCallback(
    (delivery: Delivery) => {
      update(delivery.alert_id, (detail) => {
        const existing = detail.deliveries.find((item) => item.id === delivery.id);
        if (existing && Date.parse(delivery.updated_at) < Date.parse(existing.updated_at)) {
          return detail;
        }
        const others = detail.deliveries.filter((item) => item.id !== delivery.id);
        return { ...detail, deliveries: [...others, delivery].sort((a, b) => a.id - b.id) };
      });
    },
    [update],
  );

  const isCurrent = state.alertId === alertId;
  return {
    detail: isCurrent ? state.detail : null,
    isLoading: alertId !== null && (!isCurrent || (state.detail === null && state.error === null)),
    error: isCurrent ? state.error : null,
    applyAlert,
    applyAudit,
    applyDelivery,
    reload: () => {
      void load();
    },
  };
}
