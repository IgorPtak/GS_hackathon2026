# Changelog

One line per task: `- <ID> <title>: <what changed>`. Newest at the bottom.

- S-00 contracts v1: Pydantic contracts, generated JSON Schemas and OpenAPI components, config examples, reconstructed fixtures.
- S-02 initial migration: 11 tables from contracts/storage.md with partial indexes (unrelayed outbox, open alerts, pending approval codes)
- S-01 contract generator: scripts/generate_contracts.py regenerates contracts/schemas, openapi components.schemas (paths untouched) and web/src/api/schema.gen.ts; --check detects drift, validates $refs and config examples.
- B-00 web scaffold: Vite + React + TS strict + Tailwind + ESLint/Prettier, tab layout, TeamPicker from GET /api/v1/config, openapi-fetch client, nginx Dockerfile with API proxy.
- S-03 seed demo configuration: full demo set in config/, loadtest/fixtures, scripts/validate_config.py.
- B-08 hour-1 LLM check: Qwen3.8-27B @ llm.hpc.psnc.pl (OpenAI-compatible, json_schema), 4.7/4.5/4.7 s, median 4.7 s, 3/3 valid, restart-pricing-adapter approval=required.
- S-00 contracts v1 frozen: hour-0 review applied (A1–A7, B2–B8, hybrid LLM endpoint); further changes only via feat(contracts) commits acked by both people
- A-00 Python workspace, compose stack, Makefile: uv workspace (alerting_contracts, alerting_core), one Python image, compose services with /healthz stubs, Prometheus and Grafana config, Makefile targets.
- A-02 alerting_core foundation: Settings, JSON logging, parse_duration, asyncpg/Redis factories, Prometheus helpers, StreamConsumer (ack after success, XAUTOCLAIM > 30 s idle, <stream>-dlq after 5 deliveries)
- A-04 ingest: ingest service with POST /api/v1/ingest/{source_id} and /batch, idempotency via SET NX, source plugin registry and webhook source, /metrics.
- A-01 smoke test: cumulative per-gate end-to-end checks (3h/7h/11h/14h) in scripts/smoke_test.py.
- B-05 RecentEventsPanel: polls /api/v1/events/recent every 2 s (paused while hidden) with source filter, collapsible JSON payload and error banner; Schemas and Alerts tabs.
- B-10 action plugins: registry + http_get, webhook (YAML-only), retry_workflow, restart_service, open_ticket, escalate; every config/actions/*.yaml resolves to a plugin.
- B-08 LLM client: alerting_core.llm LlmClient (OpenAI-compatible, json_schema output, one validation retry, think-block strip, LLM_ALLOWED_HOSTS), Luhn-aware redact_secrets, in-memory/Redis cache, LlmConfig.from_settings, scripts/check_llm.py.
- A-03 config: YAML loader per kind, Postgres config_documents store with atomic startup sync, hot-reloading ConfigRegistry (subscribe-then-load, coalesced reloads, per-document validation, 30 s reconcile) and one-process file watcher.
- A-19 alert storage: keyset-paginated list_alerts, get_alert_detail, acknowledge/resolve transitions with audit, outbox enqueue helpers, SSE publish helpers, uuid7.
- A-11 outbox relay: FOR UPDATE SKIP LOCKED batches to deliveries/runbook-jobs, delivery_id = outbox id, invalid rows to <stream>-dlq, lag and batch metrics.
- A-14 mock gateway: /sms, /phone, /workflows retry and service restart endpoints with outage toggles for demos.
- A-05 generator: synthetic event generator for fixtures and load scenarios.
- A-10 routing: recipients x channels from rule routes and preferences (working hours with DST, ui once), per-recipient throttle that fails open.
