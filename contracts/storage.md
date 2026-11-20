# Storage contract — Redis and Postgres names

Owner of each writer in brackets: [A] backend track, [B] UI/runbooks/LLM track.

## Redis streams and consumer groups

| Stream | Entry fields | Written by | Consumer group | Read by | Trimming |
|---|---|---|---|---|---|
| `events` | `envelope` = `EventEnvelope` JSON | ingest [A] | `processors` | processor [A]; rule preview and schema-profile test read with `XRANGE` [B via `alerting_core.event_log`] | `XTRIM MINID ~` now − 2 h, every 60 s by processor |
| `deliveries` | `job` = `DeliveryJob` JSON | outbox relay [A] | `delivery-workers` | delivery [A] | `MAXLEN ~ 1000000` |
| `runbook-jobs` | `job` = `RunbookJob` JSON | outbox relay [A] | `runbook-runners` | runbook runner [B] | `MAXLEN ~ 100000` |
| `events-dlq` | `envelope`, `error`, `attempts` | processor, ingest log-tail [A] | — | UI/ops | `MAXLEN ~ 100000` |
| `deliveries-dlq` | `job`, `error`, `attempts` | delivery [A] | — | UI/ops | `MAXLEN ~ 100000` |
| `runbook-jobs-dlq` | `job`, `error`, `attempts` | runbook runner [B] | — | UI/ops | `MAXLEN ~ 100000` |

Consumers: name = `<service>-<hostname>-<pid>`. Read with `XREADGROUP COUNT 100 BLOCK 1000`.
Pending entries idle > 30 s are taken over with `XAUTOCLAIM` by any consumer in the group.
DLQ rule (one path in `alerting_core.streams.StreamConsumer`): an entry delivered 5 times without
an ack is copied to `<stream>-dlq` with its original fields plus `error` and `attempts`, then acked.
Retries with backoff: the delivery worker acknowledges the failed entry and re-adds the job with
`not_before` in a sorted set `delivery-retries` (score = due time in ms); a poller moves due jobs back
to `deliveries`.

## Redis keys

| Key | Type | TTL | Purpose | Owner |
|---|---|---|---|---|
| `ingest-idempotency:<idempotency_key>` | string `SET NX` | 24 h | Drop duplicate submissions at ingest | A |
| `dedup:<rule_id>:<fingerprint>` | string (alert id) `SET NX` | dedup window | First event wins and creates the alert. The value is the alert id generated *before* `SET NX`; the insert is `ON CONFLICT (id) DO NOTHING`, so a redelivered event recreates an alert lost to a crash between `SET NX` and commit. On a key miss while an open alert with the same (`rule_id`, `fingerprint`) exists, the key is re-armed with that alert's id and the event folds into it | A |
| `dedup-count:<rule_id>:<fingerprint>` | counter `INCR` | dedup window + 60 s | Events folded into the alert; flushed to `alerts.count` in batches | A |
| `group-buffer:<rule_id>:<group_key>` | list `RPUSH` (event summary JSON) | group window + 60 s | Different events waiting for the group window | A |
| `group-deadlines` | sorted set, member `<rule_id>:<group_key>`, score = flush time ms | — | Flusher claims due groups with `ZREM` (returns 1 = this worker owns it) | A |
| `throttle:<rule_id>:<recipient_id>:<period_start>` | counter `INCR` | throttle period | Per-recipient delivery limit | A |
| `delivery-done:<delivery_id>` | string `SET NX` | 7 d | Delivery idempotency by outbox id | A |
| `delivery-retries` | sorted set (job JSON, score = due ms) | — | Delayed retries | A |
| `circuit:<channel_id>` | hash `{state, opened_at, failures}` | — | Circuit breaker per channel | A |
| `silence-deadlines` | sorted set, member alert id, score = deadline ms | — | Auto-resolve after silence | A |
| `log-tail-lock:<source_id>` | string (owner token) `SET NX PX` | 10 s, renewed every 3 s | Exactly one ingest process tails a log file; a crashed owner hands over after the TTL | A |
| `log-tail-offset:<source_id>` | string `<inode>:<byte offset>` | — | Resume point after the last appended batch; tail-line idempotency key is `<source_id>:<inode>:<line offset>` | A |
| `llm-cache:<sha256 of model + prompt>` | string JSON | 7 d | LLM result cache | B |

## Redis pub/sub channels

| Channel | Payload | Publisher | Subscriber |
|---|---|---|---|
| `config.changed` | `ConfigChangedEvent` | api / config watcher | every worker (reload) and api (SSE `broadcast`) |
| `alerts.team.<team_id>` | `SseEvent` (incl. `audit.appended` from every audit writer) | processor, delivery, runbook runner, api | api SSE endpoint |
| `broadcast` | `SseEvent` (`unknown_schema.detected`, `config.changed`, `phone.message`) | processor, delivery, api | api SSE endpoint |

Pub/sub is best-effort; the UI refetches lists on SSE reconnect.

## Postgres tables

Migrations live in `deploy/postgres/migrations/` (shared path, contract rule applies). `jsonb` columns
hold the contract model of the same name.

| Table | Columns | Notes |
|---|---|---|
| `config_documents` | `kind text`, `id text`, `team text null`, `document jsonb`, `yaml text`, `version int`, `updated_at timestamptz`, `updated_by jsonb` · PK (`kind`, `id`) | All config kinds incl. runbooks (`document` = `Runbook`) |
| `alerts` | `id uuid pk`, `rule_id`, `team`, `schema_profile_id`, `source_id`, `fingerprint`, `group_key`, `is_group_summary bool`, `group_members jsonb`, `severity`, `title`, `body`, `fields jsonb`, `color`, `count int`, `first_seen`, `last_seen`, `status`, `runbook_id`, `last_event jsonb`, `acknowledged_by jsonb`, `acknowledged_at`, `resolved_by jsonb`, `resolved_at`, `resolution_reason`, `updated_at` | Index (`team`, `status`, `last_seen desc`); index (`rule_id`, `fingerprint`) where `status <> 'resolved'` |
| `outbox` | `id bigserial pk`, `kind`, `alert_id uuid`, `payload jsonb`, `created_at`, `relayed_at null` | Partial index on `id` where `relayed_at is null`; relay uses `FOR UPDATE SKIP LOCKED LIMIT 500` |
| `deliveries` | `id bigint pk` (= outbox id), `alert_id`, `team`, `recipient_id`, `channel_id`, `channel_type`, `purpose`, `status`, `attempt int`, `last_error`, `is_fallback bool`, `created_at`, `updated_at`, `delivered_at` | Inserted by the relay in the same transaction that marks the outbox row relayed |
| `audit_entries` | `id bigserial pk`, `alert_id`, `at`, `actor jsonb`, `verb`, `outcome`, `detail jsonb` | Append-only |
| `action_runs` | `id uuid pk`, `alert_id`, `runbook_id`, `step_index`, `action_id`, `params jsonb`, `status`, `attempt`, `result jsonb`, `error`, `requested_by jsonb`, `created_at`, `updated_at` | |
| `approval_requests` | `id uuid pk`, `action_run_id`, `alert_id`, `team`, `runbook_id`, `step_index`, `action_id`, `params jsonb`, `summary`, `approval_code char(4)`, `requested_at`, `decision`, `decided_by jsonb`, `decided_via`, `decided_at`, `comment` | Unique (`approval_code`) where `decision is null` |
| `fix_proposals` | columns of `FixProposal` | |
| `runbook_revision_proposals` | columns of `RunbookRevisionProposal` | cut-1 |
| `unknown_schema_samples` | `shape_hash text pk`, `source_id`, `key_paths text[]`, `sample_event jsonb`, `event_count int`, `first_seen`, `last_seen` | |
| `phone_messages` | columns of `PhoneMessage` | Written by sms/phone channels for the phone simulator |
