/** Typed copies of `contracts/fixtures/events/*.json` with builders that stamp fresh IDs. */

export interface RatesTradeRejectedEvent {
  readonly meta: {
    readonly schema: string;
    readonly producer: string;
    readonly ts: number;
  };
  readonly payload: {
    readonly tradeId: string;
    readonly desk: string;
    readonly reason: string;
    readonly currency: string;
    readonly notional: number;
    readonly counterparty: string;
    readonly trader: string;
  };
}

export interface SettlementsWorkflowFailedEvent {
  readonly eventType: string;
  readonly workflowId: string;
  readonly service: string;
  readonly severity: string;
  readonly timestamp: string;
  readonly attempt: number;
  readonly error: {
    readonly code: string;
    readonly message: string;
  };
}

export interface UnknownPaymentEvent {
  readonly evt: string;
  readonly lvl: string;
  readonly svc: string;
  readonly at: string;
  readonly schemaHint?: string;
  readonly data: {
    readonly paymentId: string;
    readonly amount: number;
    readonly currency: string;
    readonly declineCode: string;
  };
}

/** From `contracts/fixtures/events/rates_trade_rejected.json`. */
export const RATES_TRADE_REJECTED_FIXTURE: RatesTradeRejectedEvent = {
  meta: {
    schema: "trade.rejected.v1",
    producer: "rates-oms",
    ts: 1795168502123,
  },
  payload: {
    tradeId: "T-20261120-000417",
    desk: "rates",
    reason: "LIMIT_BREACH",
    currency: "EUR",
    notional: 25000000,
    counterparty: "CPTY-0042",
    trader: "jdoe",
  },
};

/** From `contracts/fixtures/events/settlements_workflow_failed.json`. */
export const SETTLEMENTS_WORKFLOW_FAILED_FIXTURE: SettlementsWorkflowFailedEvent = {
  eventType: "WORKFLOW_FAILED",
  workflowId: "wf-settle-20261120-0042",
  service: "settlement-engine",
  severity: "CRITICAL",
  timestamp: "2026-11-20T10:15:00Z",
  attempt: 3,
  error: {
    code: "UPSTREAM_TIMEOUT",
    message: "Custodian API did not respond within 30s",
  },
};

/** From `contracts/fixtures/events/unknown_payments.json`. */
export const UNKNOWN_PAYMENTS_FIXTURE: UnknownPaymentEvent = {
  evt: "payment.declined",
  lvl: "WARN",
  svc: "payments-api",
  at: "2026-11-20T10:30:00+01:00",
  data: {
    paymentId: "P-99812",
    amount: 1250.0,
    currency: "PLN",
    declineCode: "INSUFFICIENT_FUNDS",
  },
};

function shortId(): string {
  return crypto.randomUUID().slice(0, 8);
}

/** Builds a fresh rates trade-rejected event with a unique tradeId and reason. */
export function buildFreshRatesAlert(tag = "ALERT"): {
  readonly event: RatesTradeRejectedEvent;
  readonly tradeId: string;
} {
  const id = shortId().toUpperCase();
  const tradeId = `T-${tag}-${id}`;
  return {
    tradeId,
    event: {
      meta: { ...RATES_TRADE_REJECTED_FIXTURE.meta, ts: Date.now() },
      payload: {
        ...RATES_TRADE_REJECTED_FIXTURE.payload,
        tradeId,
        reason: `LIMIT_BREACH_${id}`,
      },
    },
  };
}

/** Builds a fresh settlements failure with a new workflowId so retries fail and escalation triggers. */
export function buildFreshSettlementsFailure(): {
  readonly event: SettlementsWorkflowFailedEvent;
  readonly workflowId: string;
} {
  const workflowId = `wf-demo-${shortId()}`;
  return {
    workflowId,
    event: {
      ...SETTLEMENTS_WORKFLOW_FAILED_FIXTURE,
      workflowId,
      timestamp: new Date().toISOString(),
    },
  };
}

/** Builds a never-seen unknown JSON payload for generic-webhook and Connect a system. */
export function buildFreshUnknownSample(): {
  readonly event: Record<string, unknown>;
  readonly sampleId: string;
} {
  const suffix = shortId();
  const sampleId = `P-${suffix.toUpperCase()}`;
  return {
    sampleId,
    event: {
      ...UNKNOWN_PAYMENTS_FIXTURE,
      evt: `payment.declined.${suffix}`,
      at: new Date().toISOString(),
      jurySampleTag: `jury-${suffix}`,
      data: {
        ...UNKNOWN_PAYMENTS_FIXTURE.data,
        paymentId: sampleId,
      },
    },
  };
}
