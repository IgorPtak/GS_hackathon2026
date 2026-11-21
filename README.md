# Flexible Alerting & Notification Service

Teams change alerts without fear and without code, and the AI only proposes.

Flexible Alerting & Notification Service ingests events from HTTP webhooks (including Prometheus Alertmanager) and tailed log files into Redis Streams (`events`), evaluates YAML rules and schema profiles in stateless `processor` workers, persists alerts and outbox rows atomically in Postgres, relays them (`FOR UPDATE SKIP LOCKED`) to Redis Streams (`deliveries` and `runbook-jobs`), and dispatches deliveries through pluggable channels (`ui`, `email`, `sms`, `phone`, `webhook`) while running automated or human-approved runbook actions. Schema profiles, rules, recipients, channel preferences, channels, runbooks, and actions are YAML configuration synced to Postgres and hot-reloaded across every worker via Redis pub/sub (`config.changed`) with no restart; a new source of an existing type is one YAML file in `config/sources/`, also with no restart. The LLM never runs on the hot path; it is used only at save time for free-text runbooks and for proposals that a human approves.

```text
Webhook / Alertmanager / Log tail
        │
        ▼
  proxy (nginx :8000 / :8001 ──▶ api / ingest replicas)
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

## Quickstart: three commands

You need Docker Desktop (or Docker Engine with Compose v2). The running stack uses about 0.8 GB of memory, and its images take about 2.8 GB of disk.

```bash
git clone https://github.com/IgorPtak/GS_hackathon2026.git && cd GS_hackathon2026
cp .env.example .env
docker compose up -d --build
```

| Step | Measured on an Apple M4 laptop |
|---|---|
| First run: download the base images, then build | depends on your connection; the build itself takes about 25 s |
| Every later start, from `docker compose up` to all services healthy | **18 s** |
| Test event in, alert in the Inbox and the email in Mailpit | **about 1 s** |

Then open **http://localhost:5173** and pick a person, for example *Anna Kowalska* (Team Rates).
A three-step welcome explains the screens. Its last button sends a test alert, and you see it land
in the Inbox. That is the whole demo setup. Nothing has to be configured first: the `config/`
folder ships four example teams, their rules, people and runbooks.

Optional:

```bash
uv run python scripts/reset_demo.py --seed   # clean slate plus a few demo alerts and one approval
uv run python scripts/smoke_test.py --gate 14h   # end-to-end check: ingest, dedup, email, SMS, runbooks, approvals
docker compose up -d --scale processor=4 --scale delivery=4 --scale ingest=3 --scale api=2  # scale stateless services behind proxy
docker compose --profile local-llm up -d --build  # also start a local Ollama for the AI features
```

For the scene-by-scene demo walkthrough, see [docs/demo.md](docs/demo.md).

## Your first alert

**From the UI.** Home shows a *Set up your team* checklist. Each step ticks itself once it really
works, because it is read from live data, not from clicks. The last step, **Send a test alert**,
puts an alert in your Inbox. More scenarios are in the **test console** (press `Shift` + `D`
anywhere): a payment workflow that calls the on-call phone, a 500-event duplicate storm, an SMS
outage, and an unknown system.

**From a terminal.** Any system that can send an HTTP POST can send alerts:

```bash
curl -X POST localhost:8001/api/v1/ingest/rates-oms \
  -H 'content-type: application/json' \
  -d @contracts/fixtures/events/rates_trade_rejected.json
```

The event matches the `rates-large-rejections` rule. It shows up in Team Rates' Inbox, and Anna gets
an email (see http://localhost:8025). Send it again, even 500 times within the rule's 60 s dedup
window, and it is still **one** alert with a count, and no second email.

## A new team, from nothing to its first alert in about 5 minutes

We timed this path end to end with a made-up *Team Payments*. The alert and its email arrived
about 1 s after the first event.

1. **Say who the team is (two small files, 1 minute).** Then run `docker compose restart api`,
   which loads them in about 4 s.

   ```yaml
   # config/teams/payments.yaml
   id: payments
   display_name: Team Payments
   on_call: [ola]
   ```

   ```yaml
   # config/recipients/ola.yaml
   id: ola
   display_name: Ola Nowak
   teams: [payments]
   contacts: { email: ola@example.com }
   channel_preferences:
     - channels: [email, ui]
   ```

2. **Sign in as Ola.** The welcome and the *Set up Payments* checklist on Home take it from here.
3. **Connect a system (1 to 2 minutes).** Send one real event to
   `POST /api/v1/ingest/generic-webhook`, or paste it on **Connect a system**. Beacon proposes how to
   read its fields: severity, time, and what makes two events "the same". **Test on the last hour**
   shows what it would have matched before you save.
4. **Write a rule (2 minutes).** Go to **Rules → New rule**. It is a form ("field *evt* is
   *payment.declined*", "at least severity *warning*", "between hours 08:00 and 20:00"). The YAML
   view sits behind *Advanced*. **Preview** replays the last hour of events, so you see how many
   alerts and emails the rule *would* have produced before it is live. Saving reloads every worker;
   nothing restarts.
5. **Choose who is told.** On **People & channels**, set email, SMS or a call, and the working hours
   for each person.
6. **Send the event again.** The alert is in Ola's Inbox and her email arrives about 1 s later.

Everything the UI saves is versioned YAML, so the same setup can live in Git. A rule file in
`config/rules/` is the same rule as one made in the editor.

## Finding your way around the UI

There is no password on purpose. On the sign-in screen you pick who you are, and Beacon opens that
person's team.

| Screen | What it is for |
|---|---|
| **Home** | The team at a glance: the setup checklist, whether the pipeline is healthy, open alerts, waiting approvals. |
| **Inbox** | Alerts for your team, mail-style. A row shows how many times the alert repeated. The detail pane has the readable description, **Acknowledge** ("I'm on it"), **Resolve** ("it's fixed"), the runbook with its steps, who was told and how, and the audit trail. **Propose a fix** suggests a change to the rule or runbook. A teammate must accept it in Approvals. |
| **Approvals** | Runbook steps that need a human ("restart the pricing adapter?") and proposed fixes as a before/after diff. Approve or reject; the result stays visible for a moment so you see what you did. The same request can be approved from the on-call phone with a 4-digit code. |
| **Rules** | Your team's rules. The editor is a step-by-step form with a live **Preview** on past events, and the YAML is under *Advanced* (with autocomplete). |
| **Connect a system** | Three steps: pick a sample event (unknown shapes collect here on their own), check the proposed field mapping, then test and save. |
| **Runbooks** | What to do when an alert fires, written as YAML, Markdown or plain sentences. Plain text is turned into steps by the AI once, at save time. Steps that touch production always wait for approval. |
| **People & channels** | Who is told, by which channel, and in which working hours. |
| **Insights** | Throughput, end-to-end p50/p99, where the time goes per stage, and each channel's health. A channel that is down shows as *Paused*, with how many messages are waiting; none are lost. |
| **Settings** | Appearance (light, dark, automatic), the phone's voice, reopening the welcome and checklist, and links to the API docs, Grafana and Mailpit. |
| **Test console** (`Shift` + `D`) | Demo scenarios, the live raw event stream, and the on-call phone. The phone rings, reads the alert and the approval code aloud, and accepts the code on its keypad. On a real phone, open `/phone`. |

## Service URLs

| Service | URL | Purpose |
|---|---|---|
| Web UI | http://localhost:5173 | The Beacon console |
| API (`proxy`) | http://localhost:8000 | REST + SSE API for the UI (behind `proxy`, so `--scale api=N` works) |
| API docs | http://localhost:8000/docs | Interactive OpenAPI (Swagger) reference |
| Ingest (`proxy`) | http://localhost:8001 | HTTP event ingestion (`POST /api/v1/ingest/{source_id}` and `/batch`, behind `proxy` so `--scale ingest=M` works) |
| Mailpit | http://localhost:8025 | Local inbox that captures every `email` delivery |
| Grafana | http://localhost:3000 | Provisioned **Alerting** dashboard (msg/s, stream lag, p50/p95/p99 latency, retries, DLQ) |
| Prometheus | http://localhost:9090 | Metrics store that scrapes all service replicas through Compose DNS |
| Mock gateway | http://localhost:8090 | Simulated SMS/phone gateway, webhook receiver, action targets, and outage controls |

## What is mocked

| Real-world part | In this demo | To make it real |
|---|---|---|
| Email provider | Mailpit (`http://localhost:8025`, real SMTP on port 1025; nothing leaves the machine) | Update SMTP settings in `config/channels/email.yaml` |
| SMS and phone provider | Mock gateway (`services/mock_gateway`, port 8090) + on-call phone simulator (test console, or `/phone` on a real phone) with ringing, speech-synthesis read-out, 4-digit keypad approval codes, and SMS replies (`APPROVE <code>`) | Add one channel plugin in `plugins/channels/` (e.g., Twilio) |
| Runbook action targets | Mock action plugins in `plugins/actions/` (`retry_workflow`, `restart_service`, `open_ticket`, `escalate`, `http_get`, `webhook`) configured in `config/actions/` against `mock-gateway` | Point `config/actions/*.yaml` URLs at real endpoints or add a plugin in `plugins/actions/` |
| Slack / Teams / PagerDuty | Generic `webhook` channel (`config/channels/slack-rates.yaml`) posting templated JSON to `mock-gateway` (`/webhooks/{name}`) | Set the target webhook URL and `body_template` in YAML |
| Event producers | Synthetic generator (`loadtest/generator.py`), event fixtures (`contracts/fixtures/events/`), local tailed log file (`data/logs/pricing_engine.log`), and Alertmanager webhook payloads | Point real producers, Alertmanager, and log paths at `config/sources/*.yaml` |

## Load-test results

Full methodology, historical baselines, and raw result references are in [docs/load-test-results.md](docs/load-test-results.md); detailed per-benchmark tables, Postgres per-stage latency, backend query profiles, and interactive `py-spy` CPU flame graphs are in [docs/benchmarks.md](docs/benchmarks.md).

Headline (measured **2026-11-21**, commit `15dbce7`, Apple M4 10 cores / 16 GB RAM, Docker Desktop VM 10 CPUs / 7.75 GiB RAM): **800.0 msg/s sustained (1,600 deliveries/s) with p50 416.9 ms / p99 1,000.7 ms (`2:2:2:1` behind `proxy`), peak 983.8 msg/s (`1:2:1:1`, not sustainable: p99 10.9 s), steady 200 msg/s at p50 41.1 ms / p99 83.8 ms, and 0 lost alerts across every scenario**, including a 60 s gateway outage, `docker kill` of a processor mid-load, and a 120 s soak test.

| Scenario | Target msg/s | Config (`p:d:i:r`) | Sent | Delivered | Lost | p50 | p99 | Achieved msg/s |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| Steady 60 s (host → `proxy:8001`) | 200 | `1:2:1:1` | 12,000 | 24,000 / 24,000 | **0** | **41.1 ms** | **83.8 ms** | 200.0 |
| Soak 120 s (in-network) | 250 | `1:2:1:1` | 30,000 | 60,000 / 60,000 | **0** | **43.2 ms** | **461.3 ms** | 250.0 |
| Dup storm | 1,000 | `1:2:1:1` | 5,000 | 2 / 2 (1 alert, count 5,000) | **0** | n/a | n/a | 781.7 |
| Gateway down (60 s SMS outage) | 100 | `1:2:1:1` | 9,000 | 18,000 / 18,000 | **0** | 57.2 ms (`ui` 38.5 ms) | 68.6 s (`sms` 69.4 s) | 100.0 |
| Kill processor (`docker kill`) | 200 | `2:2:1:1` → `1` | 12,000 | 24,000 / 24,000 | **0** | **40.6 ms** | **134.9 ms** | 200.0 |

Horizontal scale sweep behind `proxy:8001` (`final-r500`, `final-r800`, `final-r1100`, 30 s/step, 0 lost in every cell): `2:2:2:1` sustains **500.0 msg/s** (p99 **353.2 ms**) and **800.0 msg/s** (p99 **1,000.7 ms**, max `events` lag `9`), while `4:4:3:2` eliminates delivery-stage lag (360.7 ms delivery p99) before saturating the shared 10-vCPU VM at ingest (628.2 msg/s at target 800, 608.7 msg/s at target 1,100); `1:2:1:1` peaks at **983.8 msg/s** under a 1,100 msg/s target. Replacing Redis `SCAN` in the orphan fold sweeper with `dedup-count-index` eliminated `SCAN` (**0** calls across the 72k-event 800 msg/s sweep vs 9.6 s/30 s before, dropping Redis CPU from 94% to 24.4%).

Recovery integration tests (`uv run pytest -m integration tests/integration -q`): 200 SMS sent through a gateway outage are all delivered, and `docker kill` of one of two delivery workers loses and duplicates nothing.

Reproduce with:

```bash
uv run python loadtest/scenarios.py steady --duration 60
uv run python loadtest/soak_and_scale.py --mode scale --rate 800 --duration 30 --pairs "1:2:1:1,2:2:2:1,4:4:3:2" --label final-r800
```

## How we used AI

- **During the build:** Claude Code orchestrated the implementation across subagents and ran code reviews; Gemini assisted with code reviews and documentation. All AI-generated code went through unit/integration tests, linting, and review. No production data or secrets were sent to cloud tools; all demo data is synthetic.
- **Inside the product:** The LLM is invoked only at save time (normalizing free-text runbooks into structured steps on `PUT /api/v1/runbooks/{id}`) and for proposals. The hot path (`ingest` → `processor` → `outbox-relay` → `delivery`) never calls the LLM.
- **Privacy and safety:** `alerting_core.llm.LlmClient` speaks the OpenAI-compatible `/chat/completions` API with schema-constrained JSON validated by Pydantic. It defaults to local Ollama (`http://ollama:11434/v1`); for the hackathon demo, an allowlisted cloud host (PSNC) is opted in explicitly via `LLM_ALLOWED_HOSTS` (the client refuses any host outside `LLM_ALLOWED_HOSTS`). `redact_secrets` runs before every LLM call to mask tokens, passwords, keys, and card numbers. Every LLM output is a proposal that a human reviews and approves, and when the LLM is unavailable the system degrades cleanly (free-text runbooks fall back to a single text step).

## Known limitations

- **Redis is a single point of failure** in this single-node Compose deployment (it holds the `events` / `deliveries` / `runbook-jobs` streams, dedup keys, group buffers, and pub/sub). In production, run Redis Sentinel or Redis Cluster, or replace the stream transport with Kafka or Redpanda partitioned by alert `fingerprint` (so dedup for a given alert stays on one processor partition), and add a Postgres standby replica.
- **At-least-once plugin side effects on a crash:** Delivery workers guard sends with `delivery-done:<id>` (24 h TTL) and the runbook runner records `(alert_id, step_index, attempt)` in Postgres, so normal retries are idempotent; however, if a worker crashes after an external channel or action call succeeds but before its completion is recorded, the redelivered job can repeat the side effect.
- **`events` retention waits for the slowest group:** `events` is trimmed only below the oldest position any consumer group still needs, so an abandoned consumer group makes the stream grow without bound.
- **No authentication:** Team selection is a UI dropdown by design for the demo.

## Repository layout

```text
config/         Runtime YAML configuration (sources, schemas, rules, recipients, teams, channels, runbooks, actions)
contracts/      Shared Pydantic models, OpenAPI spec, generated JSON Schemas, and event fixtures
deploy/         Dockerfiles, nginx proxy config, Postgres migrations, Prometheus config, and Grafana dashboard
docs/           Architecture plan, domain glossary, demo script, load-test results, benchmarks, and flame graphs (`docs/profiles/`)
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
