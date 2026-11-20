# Flexible Alerting & Notification Service

Teams change alerts without fear and without code, and the AI only proposes.

Flexible Alerting & Notification Service ingests events from HTTP webhooks (including Prometheus Alertmanager) and tailed log files into Redis Streams (`events`), evaluates YAML rules and schema profiles in stateless `processor` workers, persists alerts and outbox rows atomically in Postgres, relays them (`FOR UPDATE SKIP LOCKED`) to Redis Streams (`deliveries` and `runbook-jobs`), and dispatches deliveries through pluggable channels (`ui`, `email`, `sms`, `phone`, `webhook`) while running automated or human-approved runbook actions. Schema profiles, rules, recipients, channel preferences, channels, runbooks, and actions are YAML configuration synced to Postgres and hot-reloaded across every worker via Redis pub/sub (`config.changed`) with no restart. The LLM never runs on the hot path; it is used only at save time for free-text runbooks and for proposals that a human approves.

```text
Webhook / Alertmanager / Log tail
        │
        ▼
  ingest (FastAPI) ──▶ Redis Streams: events
                              │
                              ▼
                     processor workers  ◀── config/ YAML ──▶ Postgres (config_documents)
                     (profiles, rules,                         │  Redis pub/sub: config.changed
                      dedup, grouping)                         ▼ (hot reload, no restart)
                              │
                              ▼  (one Postgres transaction)
                  alerts + audit_entries + outbox
                              │
                              ▼
                  outbox-relay (FOR UPDATE SKIP LOCKED)
                     ├──▶ Redis Streams: deliveries   ──▶ delivery workers ──▶ channel plugins
                     │                                     (retries, DLQ,      (ui, email, sms,
                     │                                      fallback, CB)       phone, webhook)
                     └──▶ Redis Streams: runbook-jobs ──▶ runbook-runner   ──▶ action plugins
                                                           (approvals)          (mock gateway /
                                                                                 YAML webhooks)
```

## Quickstart

```bash
git clone <repo> && cd <repo>
cp .env.example .env
docker compose up -d --build
```

To also start a local Ollama container (optional, off by default):

```bash
docker compose --profile local-llm up -d --build
```

Verify the full stack end-to-end with the smoke test (checks health, ingest, alerts, Mailpit email, dedup, live rule reload, SMS delivery, runbook rendering, and approval via the phone simulator):

```bash
uv run python scripts/smoke_test.py --gate 14h
```

Cumulative gates `{3h,7h,11h,14h}` are supported (`make smoke GATE=14h`). For the scene-by-scene walkthrough and demo commands, see [docs/demo.md](docs/demo.md).

## Service URLs

| Service | URL | Purpose |
|---|---|---|
| Web UI | http://localhost:5173 | Alerting console (live feed, rules, runbooks, approvals, schemas, phone simulator, metrics) |
| API | http://localhost:8000 | REST + SSE API for the UI |
| API docs | http://localhost:8000/docs | Interactive OpenAPI (Swagger) reference |
| Ingest | http://localhost:8001 | HTTP event ingestion (`POST /api/v1/ingest/{source_id}` and `/batch`) |
| Mailpit | http://localhost:8025 | Local SMTP inbox capturing all `email` channel deliveries |
| Grafana | http://localhost:3000 | Provisioned **Alerting** dashboard (msg/s, stream lag, p50/p95/p99 latency, retries, DLQ) |
| Prometheus | http://localhost:9090 | Metrics store scraping all service replicas via Compose DNS |
| Mock gateway | http://localhost:8090 | Simulated SMS/phone gateway, webhook receiver, action targets, and outage controls |

## UI tabs

There is no authentication; pick a team (`Team Rates`, `Team Settlements`, `Team Pricing`, `Team Platform`) from the header dropdown.

| Tab | What it shows |
|---|---|
| **Alerts** | Live SSE alert feed for the selected team with status filter (`Open`, `Acknowledged`, `Resolved`, `All`), severity badges, `×count` dedup badges, and collapsible group summaries with drill-down rows. Clicking an alert opens the detail drawer with fields, **Acknowledge** / **Resolve** buttons, **Propose a fix**, the rendered runbook (live action-run status and manual **Run** buttons), per-channel deliveries, the audit timeline, and raw last-event JSON. A collapsible **Recent events** panel sits below the feed. |
| **Rules** | Team rules list with active versions, a CodeMirror YAML editor with live dot-path validation, and the **Preview** panel that backtests the draft rule over the last `15m` / `1h` / `6h` / `24h` of the `events` stream (scanned and matched events, alerts, deliveries per recipient and channel, sample titles) before saving. Below the editor, the **Recipients** section edits each team recipient's channel preferences and working hours. |
| **Runbooks** | Stored runbooks across all formats (`yaml`, `markdown`, `text`), showing step count, normalizer (`parser`, `llm` with model name, or `fallback`), and a side-by-side view of the original source next to the normalized steps. |
| **Approvals** | Live queue of pending runbook **Approvals** (approve or reject with an optional comment) and **Fix proposals** owned by the selected team, showing line diffs for proposed rule or runbook changes with accept/reject actions. |
| **Schemas** | **Unknown schema inbox** listing unmatched event shapes (source, event count, key paths) plus a **Paste a sample JSON event** box. Picking a sample opens the prefilled mapping form with a fingerprint picker, **Test on the last hour**, **Save schema profile**, and a shortcut to **Rules**, followed by the saved schema profiles list and **Recent events**. |
| **Phone** | Per-recipient phone simulator displaying live SMS and phone deliveries (`phone.message`). Incoming phone calls open a full-screen overlay with a Web Audio ring tone (with **Mute** toggle), speech-synthesis read-out of the alert and approval code, and a 4-digit keypad (`*` rejects, `#` repeats). Below the transcript sits an SMS reply box accepting `APPROVE <code>`, `REJECT <code>`, and `ACK`. |
| **Metrics** | Operational tiles refreshed every 5 s (`Ingest rate`, `Processed rate`, `Events stream lag`, `Deliveries stream lag`, `End-to-end latency p50`, `End-to-end latency p99`, `Delivery retries`, `Dead-lettered`, `Open alerts`) and an **Open Grafana** link. |

## What is mocked

| Real-world part | In this demo | To make it real |
|---|---|---|
| Email provider | Mailpit (`http://localhost:8025`, real SMTP on port 1025; nothing leaves the machine) | Update SMTP settings in `config/channels/email.yaml` |
| SMS and phone provider | Mock gateway (`services/mock_gateway`, port 8090) + **Phone** tab simulator with ringing, speech-synthesis read-out, 4-digit keypad approval codes, and SMS replies (`APPROVE <code>`) | Add one channel plugin in `plugins/channels/` (e.g., Twilio) |
| Runbook action targets | Mock action plugins in `plugins/actions/` (`retry_workflow`, `restart_service`, `open_ticket`, `escalate`, `http_get`, `webhook`) configured in `config/actions/` against `mock-gateway` | Point `config/actions/*.yaml` URLs at real endpoints or add a plugin in `plugins/actions/` |
| Slack / Teams / PagerDuty | Generic `webhook` channel (`config/channels/slack-rates.yaml`) posting templated JSON to `mock-gateway` (`/webhooks/{name}`) | Set the target webhook URL and `body_template` in YAML |
| Event producers | Synthetic generator (`loadtest/generator.py`), event fixtures (`contracts/fixtures/events/`), local tailed log file (`data/logs/pricing_engine.log`), and Alertmanager webhook payloads | Point real producers, Alertmanager, and log paths at `config/sources/*.yaml` |

## Load-test results

Full methodology, raw result files, and observations are in [docs/load-test-results.md](docs/load-test-results.md).

Measured on Apple M4 (10 cores, 16 GB RAM, Docker Desktop VM: 10 CPUs, 7.7 GB RAM) with `ingest` (2 uvicorn workers), `outbox-relay` (1), and `mock-gateway` (1):

| Scenario | Target msg/s | Processor / delivery | Sent | Delivered | Lost | p50 | p99 |
|---|---|---|---|---|---|---|---|
| Steady 60 s | 200 | 1 / 1 | 12,000 | 24,000 / 24,000 | **0** | 373 ms | 572 ms |
| Dup storm | 1,000 (5,000 events) | 1 / 1 | 5,000 | 2 / 2 (1 alert, count 5,000) | **0** | n/a | n/a |
| Gateway down (60 s outage) | 100 | 1 / 1 | 9,000 | 18,000 / 18,000 | **0** | 1,327 ms | 69.4 s |
| Kill processor (`docker kill`) | 200 | 2 / 1 | 12,000 | 24,000 / 24,000 | **0** | 405 ms | 1,131 ms |

Saturation steps (20 s per step, `delivery=1`, sustainable = `events` drained within 5 s, p99 < 2 s, lost = 0): max sustainable throughput is **250 msg/s** with p99 dropping from **1,276 ms** (1 processor) to **858 ms** (2 processors) to **621 ms** (4 processors), with **0 lost** in every run.

Reproduce with:

```bash
uv run python loadtest/scenarios.py steady --duration 60
```

## How we used AI

- **During the build:** Claude Code orchestrated the implementation across subagents and ran code reviews; Gemini assisted with code reviews and documentation. All AI-generated code went through unit/integration tests, linting, and review. No production data or secrets were sent to cloud tools; all demo data is synthetic.
- **Inside the product:** The LLM is invoked only at save time (normalizing free-text runbooks into structured steps on `PUT /api/v1/runbooks/{id}`) and for proposals. The hot path (`ingest` → `processor` → `outbox-relay` → `delivery`) never calls the LLM.
- **Privacy and safety:** `alerting_core.llm.LlmClient` speaks the OpenAI-compatible `/chat/completions` API with schema-constrained JSON validated by Pydantic. It defaults to local Ollama (`http://ollama:11434/v1`); for the hackathon demo, an allowlisted cloud host (PSNC) is opted in explicitly via `LLM_ALLOWED_HOSTS` (the client refuses any host outside `LLM_ALLOWED_HOSTS`). `redact_secrets` runs before every LLM call to mask tokens, passwords, keys, and card numbers. Every LLM output is a proposal that a human reviews and approves, and when the LLM is unavailable the system degrades cleanly (free-text runbooks fall back to a single text step).

## Known limitations

- **Redis is a single point of failure** in this single-node Compose deployment (it holds the `events` / `deliveries` / `runbook-jobs` streams, dedup keys, group buffers, and pub/sub). In production, run Redis Sentinel or Redis Cluster, or replace the stream transport with Kafka or Redpanda partitioned by alert `fingerprint` (so dedup for a given alert stays on one processor partition), and add a Postgres standby replica.
- **At-least-once plugin side effects on a crash:** Delivery workers guard sends with `delivery-done:<id>` and the runbook runner records `(alert_id, step_index, attempt)` in Postgres, so normal retries are idempotent; however, if a worker crashes after an external channel or action call succeeds but before its completion is recorded, the redelivered job can repeat the side effect.
- **No authentication:** Team selection is a UI dropdown by design for the demo.

## Repository layout

```text
config/         Runtime YAML configuration (sources, schemas, rules, recipients, teams, channels, runbooks, actions)
contracts/      Shared Pydantic models, OpenAPI spec, generated JSON Schemas, and event fixtures
deploy/         Dockerfiles, Postgres migrations, Prometheus config, and provisioned Grafana dashboard
docs/           Architecture plan, domain glossary, implementation plan, demo script, and load-test results
loadtest/       Synthetic event generator and end-to-end load-test scenarios
packages/       Shared Python library (`alerting_core`: config, events, rules, dedup, grouping, routing, runbooks, llm)
plugins/        Pluggable sources, channels, actions, and runbook format normalizers
scripts/        Smoke test, config validator, contract generator, LLM check, and DLQ replay helper
services/       Microservices: ingest, processor, outbox_relay, delivery, runbook_runner, api, mock_gateway
tests/          End-to-end Docker integration tests (channel-down and worker-kill recovery)
web/            React + TypeScript + Vite + Tailwind UI
```

## How to add a plugin

Each extension point uses a small base class and registry; adding a new source, channel, action, or runbook format takes one file and a YAML config entry (webhook channels and webhook actions need only YAML):

- Sources: [plugins/sources/README.md](plugins/sources/README.md)
- Channels: [plugins/channels/README.md](plugins/channels/README.md)
- Actions: [plugins/actions/README.md](plugins/actions/README.md)
- Runbook formats: [plugins/runbook_formats/README.md](plugins/runbook_formats/README.md)
- Runtime YAML configuration: [config/README.md](config/README.md)
