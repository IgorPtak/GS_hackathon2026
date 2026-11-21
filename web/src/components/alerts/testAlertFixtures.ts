/** Synthetic events for "Send test alert"; shaped like contracts/fixtures/events/*.json. */

interface TestAlert {
  readonly sourceId: string;
  readonly payload: Record<string, unknown>;
  /** Team that will own the resulting alert. */
  readonly teamId: string;
}

function freshSuffix(): string {
  return Date.now().toString(36).toUpperCase() + Math.floor(Math.random() * 36).toString(36);
}

function ratesTestAlert(): TestAlert {
  const suffix = freshSuffix();
  return {
    sourceId: "rates-oms",
    teamId: "rates",
    payload: {
      meta: { schema: "trade.rejected.v1", producer: "rates-oms", ts: Date.now() },
      payload: {
        tradeId: `T-UI-${suffix}`,
        desk: "rates",
        // The reason is part of the fingerprint, so each click makes a new alert, not a duplicate.
        reason: `LIMIT_BREACH_UI_${suffix}`,
        currency: "EUR",
        notional: 25000000,
        counterparty: "CPTY-0042",
        trader: "jdoe",
      },
    },
  };
}

function settlementsTestAlert(): TestAlert {
  return {
    sourceId: "settlements-engine",
    teamId: "settlements",
    payload: {
      eventType: "WORKFLOW_FAILED",
      workflowId: `wf-ui-${freshSuffix().toLowerCase()}`,
      service: "settlement-engine",
      severity: "CRITICAL",
      timestamp: new Date().toISOString(),
      attempt: 3,
      error: { code: "UPSTREAM_TIMEOUT", message: "Custodian API did not respond within 30s" },
    },
  };
}

/** A fresh test event that lands in the picked team's inbox; other teams get a Rates alert. */
export function buildTestAlert(teamId: string): TestAlert {
  return teamId === "settlements" ? settlementsTestAlert() : ratesTestAlert();
}
