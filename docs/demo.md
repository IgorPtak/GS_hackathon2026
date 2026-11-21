# 5-minute demo script

Step-by-step commands, UI clicks, and expected outcomes for each scene of the 5-minute demo video (see `docs/plan.md` and `docs/IMPLEMENTATION_PLAN.md` section 6). Scene timings add up to 5:00; the judges checklist at the end is untimed.

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

## Scene 1 (0:00–0:20) — Problem, pitch, and architecture

- **Show on screen:** Architecture diagram from [README.md](../README.md) (events → Redis Streams `events` → `processor` → Postgres `outbox` → `outbox-relay` → `deliveries` / `runbook-jobs` → channel and action plugins; YAML hot reload; LLM off the hot path).
- **Key line:** "Teams change alerts without fear and without code, and the AI only proposes."

---

## Scene 2 (0:20–1:00) — Quickstart and unknown schema onboarding

### Commands

Show the quickstart (or run against a fresh clone):

```bash
git clone https://github.com/IgorPtak/GS_hackathon2026.git && cd GS_hackathon2026
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
3. Under **Unknown schema inbox**, locate the `generic-webhook` card and click **Propose a schema** (or paste `contracts/fixtures/events/unknown_payments.json` into **Paste a sample JSON event** and click **Propose a schema**).
4. Review the prefilled mappings (`type ← evt`, `source ← svc`, `severity ← lvl`, `occurred_at ← at`, `entity ← data.paymentId`, fingerprint `[evt, svc]`).
5. Under **Test on the last hour**, click **Run test** (nothing is written), then click **Save schema profile** and **Create a rule for this schema**.

### What the viewer must see

- The unknown JSON event lands in the **Unknown schema inbox** with its key paths and count.
- **Run test** shows normalized rows (`type: payment.declined`, `source: payments-api`, `severity: warning`, `entity: P-99812`).
- Saving hot-reloads the processor without restarting any container.

---

## Scene 3 (1:00–2:20) — Rules, rule validation, runbook actions, Mailpit, and Anna's preferences

### UI clicks (rule preview, operators, and validation)

1. In the header team picker, select **Team Rates**. Open the **Rules** tab and select `rates-large-rejections`.
2. Under **Preview**, keep **Window** on **Last 1h** and click **Run preview**.
3. Make a live edit in the YAML editor (for example, adjust the `payload.notional` threshold), verify validation stays green, and click **Save** (the version badge increments, e.g. `Active version v2`).
4. **Operators (do not save):** Pick **Team Pricing** → **Rules** → `pricing-stale-feed`. Point at `{ field: level, op: severity_gte, value: warning }`: "WARN or above" matches WARN, ERROR and FATAL. Back in **Team Rates**, paste the `time_between` example from [config/README.md](../config/README.md) into `when.all` (`{ field: normalized.occurred_at, op: time_between, value: { range: "08:00-20:00", timezone: Europe/Warsaw } }`) and click **Run preview**. Validation stays green.
5. **Invalid regex:** add `{ field: msg, op: regex, value: "([" }` to `when.all` and click **Save**. Expected: HTTP 422 `validation_failed`, a field-level error on `when.all[N].value` in the editor, and no new version. Remove the line before continuing.

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

(Optional: generate mixed events with `uv run python loadtest/generator.py --rate 5 --duration 5 --mix rates:1`.)

### UI clicks (live feed, runbook actions, and Mailpit)

1. Open the **Alerts** tab → `Rejected EUR 25000000 — LIMIT_BREACH_DEMO` appears live via SSE.
2. Click the row to open the detail drawer: **Fields**, the rendered Markdown **Runbook** (`Trade limit breach`, from `config/runbooks/trade-limit-breach.md`), **Deliveries**, **Audit**, and **Propose a fix**.
3. In the runbook, click **Run** on the step with the inline action `open-ticket summary="Limit increase for CPTY-0042" team=risk` (`approval: none`). Expected: the action run reaches `succeeded` and appears in **Audit**.
4. Click **Resolve** on the alert, then trigger **Run** on the same step again. Expected: refused with HTTP 409 `alert_resolved` ("the alert is already resolved"); no new action run is created.
   - Optional API check: `curl -s -X POST http://localhost:8000/api/v1/alerts/<alert_id>/runbook/steps/<step_index>/run -H "content-type: application/json" -d '{"actor": {"id": "demo-operator"}}'` → 409 `alert_resolved`.
5. Open Mailpit at http://localhost:8025: the delivered email lists the numbered runbook steps with the values filled in (`T-20261120-DEMO01`, `CPTY-0042`, `jdoe`). SMS and phone carry only a short link.
6. Return to **Rules** → **Recipients** → **Anna Kowalska** (`anna`): show her working hours (`08:00-20:00` `Europe/Warsaw` → `sms, phone`, otherwise `email`) and click **Save preferences**.

### What the viewer must see

- **Preview** reports scanned and matched events, alerts, and deliveries per recipient and channel before anything is sent.
- `severity_gte` and `time_between` work as rule conditions, and an invalid regex is refused with a field-level 422.
- Saving a rule or preference takes effect with no service restart.
- A markdown runbook step with an inline action runs from the UI and is recorded in **Audit**; the same run is refused once the alert is resolved.
- The email lists the numbered runbook steps.

---

## Scene 4 (2:20–3:10) — `WORKFLOW_FAILED` runbook, phone ringing with keypad approval, and free-text runbook

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
   - The runbook runner executes Step 0 (`http-health-check` → HTTP 200 `succeeded`) and Step 1 (`retry-workflow`, 2 attempts → HTTP 502 `failed`), then pauses at Step 2 (`escalate`, `approval: required`, `run_if: previous_failed`).
   - Piotr's phone starts ringing with the **Incoming call** overlay.
2. Click **Answer**: the browser reads the alert and approval request aloud and shows the transcript. Enter the 4-digit approval code on the keypad (`*` rejects, `#` repeats), or reply `APPROVE <code>` in the SMS box, or approve from the **Approvals** tab.
3. Switch to **Alerts** (Team Settlements) and open `Workflow wf-settle-20261120-demo01 failed — UPSTREAM_TIMEOUT`: the **Runbook** shows Step 0 `succeeded`, Step 1 `failed`, and Step 2 `succeeded` after approval; **Audit** shows `approval_requested`, `approval_decided`, and the escalated action run.

### Free-text runbook normalized at config sync

1. Open the **Runbooks** tab and click **Stale price feed** (`pricing-stale-feed`).
2. Show the original plain-English text (`config/runbooks/pricing-stale-feed.txt`) next to the structured steps. The normalizer shows `llm` with the model name, and `restart-pricing-adapter` shows `requires approval`: the LLM cannot remove the gate.
3. The file is normalized when config syncs (cached by content hash, 15 s bound, falls back to one text step if the LLM is unavailable). Optional live re-run through the same normalizer (requires an active Ollama or allowlisted LLM endpoint):

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

- The health check and 2 retries run without human intervention; the escalation pauses for human approval.
- Piotr's phone rings, reads out the request, and the 4-digit code on the keypad runs the escalation and records it in **Audit**.
- A free-text runbook becomes executable steps with `requires approval` kept on gated actions, and the original prose stays alongside.

---

## Scene 5 (3:10–3:30) — Deduplication (`×500`) and SMS gateway outage recovery

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

1. Pick **Team Rates** → **Alerts**: a single `Rejected EUR 25000000 — DUP_STORM_DEMO` row with badge `×500`.
2. Pick **Team Settlements** → **Alerts** → open `Workflow wf-settle-20261120-outage01 failed — UPSTREAM_TIMEOUT` → **Deliveries**: while the outage is active, `sms` shows `failed` (retrying); after recovery it becomes `delivered` and appears in **Phone** → **Piotr Nowak**.

### What the viewer must see

- 500 identical events collapse into **one alert with `×500`** and one set of deliveries.
- While the SMS gateway returns HTTP 503, deliveries retry without dropping alerts; once restored, every pending SMS lands in the **Phone** tab.

---

## Scene 6 (3:30–4:10) — Metrics, Grafana, load test, and horizontal scaling

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

1. Open the **Metrics** tab at http://localhost:5173: point out the live tiles updating every 5 s (`Ingest rate`, `Processed rate`, `Events stream lag`, `Deliveries stream lag`, `End-to-end latency p50`, `End-to-end latency p99`, `Delivery retries`, `Dead-lettered`, `Open alerts`).
2. Click **Open Grafana** (http://localhost:3000) and open the provisioned **Alerting** dashboard.
3. Quote the numbers from the README load table (do not re-measure on stage), see [docs/load-test-results.md](load-test-results.md) for the full method:
   - Steady 60 s at 200 msg/s: 12,000 sent, 24,000 / 24,000 delivered, **0 lost**, p50 373 ms, p99 572 ms.
   - After the A-24 fixes, 350 msg/s: p50 56 ms, p99 163 ms, **0 lost**.
   - In-network generator at 500 msg/s: p50 81.8 ms, p99 1917.9 ms (about 1.9 s), **0 lost**.

### What the viewer must see

- Live msg/s, stream lag, and latency tiles during load.
- The horizontal scaling command and the README numbers, with zero lost alerts.

---

## Scene 7 (4:10–5:00) — Alertmanager auto-resolve, LLM privacy, and AI usage

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

1. Pick **Team Platform** → **Alerts**: `ExporterDown on exporter-demo01:9100` appears as `open`.
2. After posting the resolved webhook, set the **Status** filter to **Resolved** (or **All**) and open the alert: `status: resolved`, `resolution_reason: source_resolved`, and the audit entry from `system:processor`.
3. Close with the privacy and AI points from [README.md](../README.md): local Ollama by default, an opt-in allowlisted cloud host via `LLM_ALLOWED_HOSTS`, `redact_secrets` before every call, zero LLM calls on the hot path, synthetic data only.

### What the viewer must see

- A firing Alertmanager event opens an alert, and the matching resolved event auto-resolves it with an audit trail.
- A clear summary of how the AI is used safely: it proposes, humans approve.

---

## Live-judging checklist ("judges bring a schema and runbook")

Untimed; use it when judges bring their own material.

1. **Onboard schema:** Paste the judge's JSON in **Schemas** → **Paste a sample JSON event** → **Propose a schema** → **Run test** → **Save schema profile**.
2. **Create rule:** Click **Create a rule for this schema** (or save via `PUT /api/v1/rules/{rule_id}`), run **Preview**, and **Save**.
3. **Add runbook:** Save the judge's YAML, Markdown, or free-text runbook via `PUT /api/v1/runbooks/{runbook_id}` and inspect the normalized steps in the **Runbooks** tab.
4. **Send live event:** `POST http://localhost:8001/api/v1/ingest/generic-webhook` with the judge's JSON → watch the alert, rendered runbook, and deliveries appear live in **Alerts**.
5. **New source by YAML only (no restart):** Copy the source file and change its id, then post a fixture to the new endpoint:

```bash
sed 's/^id: generic-webhook$/id: judges/' config/sources/generic-webhook.yaml > config/sources/judges.yaml

curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8001/api/v1/ingest/judges \
  -H "content-type: application/json" \
  -d @contracts/fixtures/events/unknown_payments.json
```

   Expected: `202`, with no `docker compose restart`. Cleanup: `rm config/sources/judges.yaml`; the same POST then answers `404` because the source was removed.
