# 5-minute demo script

Step-by-step commands, UI clicks, and expected outcomes for each scene of the 5-minute demo video (see `docs/plan.md` and `docs/IMPLEMENTATION_PLAN.md` section 6).

## Before you start

1. Ensure the stack is running (`docker compose ps` shows all services healthy).
2. Open these browser tabs ahead of recording:
   - Web UI: http://localhost:5173
   - Mailpit: http://localhost:8025
   - Grafana (**Alerting** dashboard): http://localhost:3000
3. **Browser audio unlock:** Before Scene 4, click once anywhere inside the http://localhost:5173 tab so the browser permits Web Audio to play the incoming-call ring tone.
4. **Fresh IDs to avoid dedup merging across takes:** The processor deduplicates open alerts by `(rule_id, fingerprint)` inside each rule's dedup window (`60s` for the demo rules). When re-running a scene, change the fingerprint field listed below:

| Fixture (`contracts/fixtures/events/`) | Ingest endpoint | Schema profile fingerprint (`config/schemas/`) | Field to vary for a fresh alert |
|---|---|---|---|
| `unknown_payments.json` | `/api/v1/ingest/generic-webhook` | `[evt, svc]` (`generic`) | `evt` or `svc` |
| `rates_trade_rejected.json` | `/api/v1/ingest/rates-oms` | `[meta.schema, payload.desk, payload.reason]` (`trade-rejected`) | `payload.reason` |
| `settlements_workflow_failed.json` | `/api/v1/ingest/settlements-engine` | `[eventType, workflowId]` (`workflow-failed`) | `workflowId` (also resets `mock-gateway`'s 2 initial retry failures) |
| `pricing_engine.log` | Appended to `data/logs/pricing_engine.log` | `[instrument, feed]` (`pricing-log`) | `instrument` |
| `alertmanager_firing.json` / `alertmanager_resolved.json` | `/api/v1/ingest/alertmanager` | `[labels.alertname, labels.instance]` (`alertmanager`) | `labels.instance` (keep identical across firing + resolved) |

---

## Scene 1 (0:00–0:30) — Problem, pitch, and architecture

- **Show on screen:** Architecture diagram from [README.md](../README.md) (events → Redis Streams `events` → `processor` → Postgres `outbox` → `outbox-relay` → `deliveries` / `runbook-jobs` → channel and action plugins; YAML hot reload; LLM off the hot path).
- **Key line:** "Teams change alerts without fear and without code, and the AI only proposes."

---

## Scene 2 (0:30–1:15) — Quickstart and unknown schema onboarding

### Commands

Show the quickstart (or run against a fresh clone):

```bash
git clone <repo> && cd <repo>
cp .env.example .env
docker compose up -d --build
```

Send an unrecognised event shape to `generic-webhook`:

```bash
curl -s -X POST http://localhost:8001/api/v1/ingest/generic-webhook \
  -H "content-type: application/json" \
  -d @contracts/fixtures/events/unknown_payments.json
```

Expected response: HTTP 202 with `{"event_ids":["..."],"duplicate_count":0}`.

### UI clicks

1. Open http://localhost:5173 and pick a team in the top-right dropdown (needed to save a schema profile).
2. Click the **Schemas** tab.
3. Under **Unknown schema inbox**, locate the `generic-webhook` card (`evt`, `lvl`, `svc`, `at`, `data.paymentId`, …) and click **Propose a schema** (alternatively paste the contents of `contracts/fixtures/events/unknown_payments.json` into **Paste a sample JSON event** and click **Propose a schema**).
4. Review the prefilled field mappings (`type ← evt`, `source ← svc`, `severity ← lvl`, `occurred_at ← at`, `entity ← data.paymentId`, fingerprint `[evt, svc]`).
5. Under **Test on the last hour**, click **Run test** to preview matched events and normalized fields without writing anything.
6. Click **Save schema profile**, then click **Create a rule for this schema** to jump to **Rules**.

### What the viewer must see

- An unknown JSON event lands immediately in the **Unknown schema inbox** with its key paths and count.
- **Run test** displays normalized rows (`type: payment.declined`, `source: payments-api`, `severity: warning`, `entity: P-99812`).
- Saving persists the new schema profile version and hot-reloads the processor without restarting any container.

---

## Scene 3 (1:15–2:15) — Team Rates rule preview, live alert, Mailpit, and Anna's preferences

### UI clicks (rule preview and live edit)

1. In the header team picker, select **Team Rates**.
2. Open the **Rules** tab and select `rates-large-rejections`.
3. Under **Preview**, keep **Window** on **Last 1h** and click **Run preview**.
4. Make a live edit in the YAML editor (for example, adjust the `payload.notional` threshold or title template), verify validation stays green, and click **Save** (watch the version badge increment, e.g. `Active version v2`).

### Commands

Send a fresh trade-rejected event (use a unique `payload.reason` so it opens a new alert instead of folding into an earlier `LIMIT_BREACH` alert):

```bash
cat <<'EOF' > /tmp/demo_rates.json
{
  "meta": { "schema": "trade.rejected.v1", "producer": "rates-oms", "ts": 1795168502123 },
  "payload": {
    "tradeId": "T-20261120-DEMO01",
    "desk": "rates",
    "reason": "LIMIT_BREACH_DEMO",
    "currency": "EUR",
    "notional": 25000000,
    "counterparty": "CPTY-0042",
    "trader": "jdoe"
  }
}
EOF

curl -s -X POST http://localhost:8001/api/v1/ingest/rates-oms \
  -H "content-type: application/json" \
  -d @/tmp/demo_rates.json
```

(Optional: generate a stream of mixed rates events with `uv run python loadtest/generator.py --rate 5 --duration 5 --mix rates:1`.)

### UI clicks (live feed, Mailpit, and channel preferences)

1. Open the **Alerts** tab → the new alert (`Rejected EUR 25000000 — LIMIT_BREACH_DEMO`) appears live via SSE without refreshing.
2. Click the alert row to open the detail drawer: show **Fields**, the rendered Markdown **Runbook** (`Trade limit breach` with `T-20261120-DEMO01`, `CPTY-0042`, `jdoe`), **Deliveries**, **Audit**, and the **Propose a fix** button.
3. Open Mailpit at http://localhost:8025 to show the delivered email (contains the full runbook steps) when outside Anna's working hours (`08:00-20:00` `Europe/Warsaw`), or open **Phone** → **Anna Kowalska** to show SMS/phone delivery during working hours.
4. Return to **Rules** and scroll down to **Recipients** → **Anna Kowalska** (`anna`): show her preference (`08:00-20:00` `Europe/Warsaw` → `sms, phone`, otherwise `email`), adjust the working hours, and click **Save preferences** to show live preference updates.

### What the viewer must see

- **Preview** reports events scanned, events matched, alerts that would be created, deliveries per recipient and channel, and sample titles before any alert is sent.
- Saving a rule or channel preference takes effect immediately with no service restart.
- The alert arrives live in **Alerts**, with full runbook steps in Mailpit email and a short link on SMS/phone.

---

## Scene 4 (2:15–3:15) — `WORKFLOW_FAILED` runbook, phone ringing with keypad approval, and free-text runbook

### UI setup (before posting the event)

1. In the header team picker, select **Team Settlements**.
2. Open the **Phone** tab and select **Piotr Nowak** in the **Recipient** dropdown.
3. **Click once anywhere on the page** so the browser permits Web Audio playback for the ring tone.

### Commands

Post `settlements_workflow_failed.json` with a fresh `workflowId` (new fingerprint, and fresh retry counter on `mock-gateway`, which fails the first 2 retry calls with HTTP 502):

```bash
cat <<'EOF' > /tmp/demo_settlements.json
{
  "eventType": "WORKFLOW_FAILED",
  "workflowId": "wf-settle-20261120-demo01",
  "service": "settlement-engine",
  "severity": "CRITICAL",
  "timestamp": "2026-11-20T10:15:00Z",
  "attempt": 3,
  "error": {
    "code": "UPSTREAM_TIMEOUT",
    "message": "Custodian API did not respond within 30s"
  }
}
EOF

curl -s -X POST http://localhost:8001/api/v1/ingest/settlements-engine \
  -H "content-type: application/json" \
  -d @/tmp/demo_settlements.json
```

### UI clicks (phone call approval and runbook audit)

1. Watch the **Phone** tab:
   - The runbook runner automatically executes Step 0 (`http-health-check` → HTTP 200 `succeeded`) and Step 1 (`retry-workflow`, 2 attempts → HTTP 502 `failed`), then pauses at Step 2 (`escalate`, `approval: required`, `run_if: previous_failed`).
   - Piotr's phone starts ringing with the **Incoming call** overlay.
2. Click **Answer**:
   - The browser reads the alert and approval request aloud via speech synthesis and displays the transcript.
   - Enter the 4-digit approval code on the on-screen keypad (or your keyboard; `*` rejects, `#` repeats the read-out). The simulator submits `APPROVE <code>` and shows confirmation. (You can also reply `APPROVE <code>` in the SMS reply box or approve from the **Approvals** tab.)
3. Switch to **Alerts** (Team Settlements) and click `Workflow wf-settle-20261120-demo01 failed — UPSTREAM_TIMEOUT`:
   - In **Runbook**, show the original YAML source side-by-side with the rendered steps (`wf-settle-20261120-demo01` filled in): Step 0 `succeeded`, Step 1 `failed`, and Step 2 `succeeded` after Piotr's approval.
   - Scroll to **Audit** to show the full timeline (`alert_created`, `runbook_started`, action runs, `approval_requested`, `approval_decided`, and the escalated action run).

### Free-text runbook normalization (second half of Scene 4)

1. Open the **Runbooks** tab and click **Stale price feed** (`pricing-stale-feed`).
2. Show the original plain-English paragraph (`config/runbooks/pricing-stale-feed.txt`) next to the 4 structured steps produced at save time (`normalized by llm`, including `restart-pricing-adapter` marked `requires approval`).
3. Optional: to trigger LLM save-time normalization live via the API (requires an active Ollama or allowlisted LLM endpoint; otherwise falls back to a single text step):

```bash
curl -s -X PUT http://localhost:8000/api/v1/runbooks/pricing-stale-feed \
  -H "content-type: application/json" \
  -d '{
    "id": "pricing-stale-feed",
    "title": "Stale price feed",
    "team": "pricing",
    "format": "text",
    "source": "When a price for an instrument goes stale, first look at whether the whole feed is down or just one instrument. If it is just one, restart the pricing adapter for that feed (needs approval from the pricing lead). If the whole feed is down, call the market data vendor and switch to the backup feed. Afterwards tell the traders that prices are fresh again.",
    "actor": { "id": "pricing-operator" }
  }'
```

### What the viewer must see

- Automatic health check and 2 retries run without human intervention; the risky escalation pauses for human approval.
- Piotr's phone rings, reads out the approval request, and accepts the 4-digit code on the keypad to execute the escalation and record it in the audit trail.
- A free-text runbook is normalized into executable steps (preserving `requires approval` on gated actions) with the original prose kept alongside.

---

## Scene 5 (3:15–3:45) — Deduplication (`×500`) and SMS gateway outage recovery

### Commands (500 identical events → one alert `×500`)

Generate a batch of 500 identical trade-rejected events with a fresh `payload.reason` and post it to the batch endpoint:

```bash
python3 -c '
import json
evt = json.load(open("contracts/fixtures/events/rates_trade_rejected.json"))
evt["payload"]["reason"] = "DUP_STORM_DEMO"
json.dump([evt] * 500, open("/tmp/rates_500.json", "w"))
'

curl -s -X POST http://localhost:8001/api/v1/ingest/rates-oms/batch \
  -H "content-type: application/json" \
  -d @/tmp/rates_500.json
```

(Alternatively, run `uv run python loadtest/scenarios.py dup-storm --total 500` to fold 500 events under `Team Platform`.)

### Commands (SMS gateway outage and recovery)

1. Simulate an SMS gateway outage on `mock-gateway`:

```bash
curl -s -X POST http://localhost:8090/admin/outage \
  -H "content-type: application/json" \
  -d '{"is_down": true, "channels": ["sms"]}'
```

Expected response: `{"is_down":true,"channels":["sms"]}`.

2. Send a fresh settlements event (Piotr always receives `sms` regardless of working hours):

```bash
cat <<'EOF' > /tmp/demo_outage.json
{
  "eventType": "WORKFLOW_FAILED",
  "workflowId": "wf-settle-20261120-outage01",
  "service": "settlement-engine",
  "severity": "CRITICAL",
  "timestamp": "2026-11-20T10:15:00Z",
  "attempt": 3,
  "error": {
    "code": "UPSTREAM_TIMEOUT",
    "message": "Custodian API did not respond within 30s"
  }
}
EOF

curl -s -X POST http://localhost:8001/api/v1/ingest/settlements-engine \
  -H "content-type: application/json" \
  -d @/tmp/demo_outage.json
```

3. Pause a few seconds so the viewer sees the `sms` delivery in `failed` (retrying) state, then restore the SMS gateway:

```bash
curl -s -X POST http://localhost:8090/admin/outage \
  -H "content-type: application/json" \
  -d '{"is_down": false, "channels": ["sms"]}'
```

Expected response: `{"is_down":false,"channels":[]}`.

### UI clicks

1. Pick **Team Rates** → **Alerts** tab: show the single `Rejected EUR 25000000 — DUP_STORM_DEMO` row with badge `×500`.
2. Pick **Team Settlements** → **Alerts** tab → open `Workflow wf-settle-20261120-outage01 failed — UPSTREAM_TIMEOUT` → inspect **Deliveries**: while the outage is active, `sms` shows `failed` (retrying); after recovery, it transitions to `delivered` and appears in **Phone** → **Piotr Nowak**.

### What the viewer must see

- 500 identical events collapse into **one alert with `×500`** and one set of deliveries.
- While the SMS gateway returns HTTP 503, deliveries retry cleanly without dropping alerts; once restored, every pending SMS lands in the **Phone** tab with zero loss.

---

## Scene 6 (3:45–4:30) — Metrics, Grafana, load test, and horizontal scaling

### Commands

Run the steady-load scenario (60 s at 200 msg/s = 12,000 events, 24,000 deliveries):

```bash
uv run python loadtest/scenarios.py steady --duration 60
```

To demonstrate horizontal scaling of stateless workers (Prometheus discovers new replicas automatically via Compose DNS):

```bash
docker compose up -d --scale processor=4
```

(When finished scaling, return to one replica with `docker compose up -d --scale processor=1`.)

### UI clicks

1. Open the **Metrics** tab at http://localhost:5173: point out live tiles updating every 5 s (`Ingest rate`, `Processed rate`, `Events stream lag`, `Deliveries stream lag`, `End-to-end latency p50`, `End-to-end latency p99`, `Delivery retries`, `Dead-lettered`, `Open alerts`).
2. Click **Open Grafana** (http://localhost:3000) and open the provisioned **Alerting** dashboard to show time-series throughput, stream lag, and latency percentiles.
3. Reference the recorded saturation and recovery table in [docs/load-test-results.md](load-test-results.md) (p99 drops from 1,276 ms → 858 ms → 621 ms across 1 / 2 / 4 processors; 0 lost across all scenarios).

### What the viewer must see

- Live msg/s, low stream lag, and sub-second p50/p99 latency during steady load.
- Clear explanation and live/recorded evidence of horizontal scaling (`--scale processor=4`) and zero lost alerts.

---

## Scene 7 (4:30–5:00) — Alertmanager auto-resolve, LLM privacy, and AI usage

### Commands

Send a firing Alertmanager webhook (use a fresh `labels.instance` if repeating the scene), then send the matching resolved webhook:

```bash
cat <<'EOF' > /tmp/demo_am_firing.json
{
  "version": "4",
  "status": "firing",
  "receiver": "alerting-service",
  "groupKey": "{}:{alertname=\"ExporterDown\"}",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "ExporterDown",
        "severity": "critical",
        "instance": "exporter-demo01:9100",
        "job": "dynamic-monitoring"
      },
      "annotations": { "summary": "Exporter exporter-demo01:9100 is down" },
      "startsAt": "2026-11-20T10:20:00Z",
      "endsAt": "0001-01-01T00:00:00Z",
      "fingerprint": "demo01a1b2c3d4e5"
    }
  ]
}
EOF

curl -s -X POST http://localhost:8001/api/v1/ingest/alertmanager \
  -H "content-type: application/json" \
  -d @/tmp/demo_am_firing.json
```

After showing the open alert in the UI, resolve it from the source:

```bash
cat <<'EOF' > /tmp/demo_am_resolved.json
{
  "version": "4",
  "status": "resolved",
  "receiver": "alerting-service",
  "groupKey": "{}:{alertname=\"ExporterDown\"}",
  "alerts": [
    {
      "status": "resolved",
      "labels": {
        "alertname": "ExporterDown",
        "severity": "critical",
        "instance": "exporter-demo01:9100",
        "job": "dynamic-monitoring"
      },
      "annotations": { "summary": "Exporter exporter-demo01:9100 is down" },
      "startsAt": "2026-11-20T10:20:00Z",
      "endsAt": "2026-11-20T10:25:00Z",
      "fingerprint": "demo01a1b2c3d4e5"
    }
  ]
}
EOF

curl -s -X POST http://localhost:8001/api/v1/ingest/alertmanager \
  -H "content-type: application/json" \
  -d @/tmp/demo_am_resolved.json
```

### UI clicks

1. Pick **Team Platform** → **Alerts** tab: `ExporterDown on exporter-demo01:9100` appears as `open`.
2. After posting the resolved webhook, switch the **Status** filter to **Resolved** (or **All**) and open the alert to show `status: resolved`, `resolution_reason: source_resolved`, and the audit entry from `system:processor`.
3. Close with privacy and AI usage highlights from [README.md](../README.md): local Ollama default, opt-in allowlisted cloud host via `LLM_ALLOWED_HOSTS`, `redact_secrets` before every call, zero LLM calls on the hot path, synthetic data only.

### What the viewer must see

- An Alertmanager `firing` event opens an alert and the matching `resolved` event auto-resolves it with an audit trail.
- Clear summary of how AI was used safely during development and inside the product.

---

## Live-judging checklist ("judges bring a schema and runbook")

1. **Onboard schema:** Paste the judge's JSON in **Schemas** → **Paste a sample JSON event** → **Propose a schema** → **Run test** → **Save schema profile**.
2. **Create rule:** Click **Create a rule for this schema** (or save via `PUT /api/v1/rules/{rule_id}`), run **Preview**, and **Save**.
3. **Add runbook:** Save the judge's YAML, Markdown, or free-text runbook via `PUT /api/v1/runbooks/{runbook_id}` and inspect the normalized steps in the **Runbooks** tab.
4. **Send live event:** `POST http://localhost:8001/api/v1/ingest/generic-webhook` with the judge's JSON → watch the alert, rendered runbook, and deliveries appear live in **Alerts**.
