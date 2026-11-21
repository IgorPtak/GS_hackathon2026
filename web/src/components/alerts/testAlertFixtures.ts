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

function pricingTestAlert(): TestAlert {
  // Goes through the generic webhook, like the seeded pricing log line; the instrument is the
  // fingerprint, so each click makes a new alert.
  const instrument = `EURUSD-UI-${freshSuffix()}`;
  const now = new Date().toISOString();
  return {
    sourceId: "generic-webhook",
    teamId: "pricing",
    payload: {
      timestamp: now,
      level: "ERROR",
      service: "pricing-engine",
      instrument,
      feed: "reuters",
      age_ms: "31000",
      msg: "Price stale for 31s",
      raw_line: `${now} ERROR pricing-engine instrument=${instrument} feed=reuters age_ms=31000 msg="Price stale for 31s"`,
    },
  };
}

function platformTestAlert(): TestAlert {
  // Alertmanager fingerprints by alertname and instance, so the instance is fresh per click.
  const instance = `exporter-ui-${freshSuffix().toLowerCase()}:9100`;
  return {
    sourceId: "alertmanager",
    teamId: "platform",
    payload: {
      version: "4",
      status: "firing",
      receiver: "alerting-service",
      groupKey: '{}:{alertname="ExporterDown"}',
      alerts: [
        {
          status: "firing",
          labels: {
            alertname: "ExporterDown",
            severity: "warning",
            instance,
            job: "dynamic-monitoring",
          },
          annotations: { summary: `Exporter ${instance} is down` },
          startsAt: new Date().toISOString(),
          endsAt: "0001-01-01T00:00:00Z",
        },
      ],
    },
  };
}

const BUILDERS: Record<string, () => TestAlert> = {
  rates: ratesTestAlert,
  settlements: settlementsTestAlert,
  pricing: pricingTestAlert,
  platform: platformTestAlert,
};

/** A fresh test event that lands in the picked team's inbox; unknown teams get a Rates alert. */
export function buildTestAlert(teamId: string): TestAlert {
  return (BUILDERS[teamId] ?? ratesTestAlert)();
}
