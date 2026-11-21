# config

Runtime configuration loaded into Postgres (`config_documents`) and hot-reloaded across services. One subdirectory per kind.

## Conventions and validation

- Every document lives in its kind's subdirectory under `config/` with filename `<id>.yaml` (or `.yml`; **runbooks** also accept `.md` and `.txt`).
- The document `id` must match the file stem (`alerting_core.config.loader.load_config_file`). For Markdown and plain-text **runbooks**, `id` is derived from the file stem.
- Built-in kinds (`source`, `schema_profile`, `rule`, `recipient`, `team`, `channel`, `action`) are registered in `alerting_core.config.kinds`; `runbook` is registered at startup via `register_runbook_kind()` in `alerting_core.runbooks.store`.
- Invalid files are logged as `config_file_invalid` with file name and dotted field path (for example `rules/x.yaml: when.all.0.op: ...`) and skipped without blocking valid files. You can dry-run validate YAML of any kind through `POST /api/v1/config/validate`.

## Configuration kinds

### `rule`
- **Directory:** `config/rules/<id>.yaml` (`.yaml`, `.yml`)
- **JSON Schema:** [`config.Rule.schema.json`](../contracts/schemas/config.Rule.schema.json)
- Owned by a **team**; defines the `when` **condition** tree (over raw event fields and **normalized fields**), optional **severity** override, **route**, **presentation** templates, **dedup window**, optional **group window**, **throttle**, **auto-resolve** policy, and optional **runbook** reference.

**Condition operators `severity_gte` and `time_between`:**
- `severity_gte`: ranks the field and the value as `debug < info < warning < error < critical`. Aliases are case-insensitive: `WARN`, `ERR`, `FATAL`/`CRIT`, `TRACE`. `{ field: level, op: severity_gte, value: warning }` matches WARN, ERROR and FATAL. Unknown field values never match.
- `time_between`: the field is a timestamp (ISO-8601, epoch seconds or milliseconds), typically `normalized.occurred_at`. The value is `"HH:MM-HH:MM"` in UTC or `{ range: "HH:MM-HH:MM", timezone: Europe/Warsaw }`. Start is inclusive, end exclusive; `20:00-08:00` wraps midnight. A missing or unparseable timestamp never matches.
- Invalid values (unknown severity, bad range or timezone, unsafe regex) are reported by `alerting_core.rules.validate_rule` with a path such as `when.all[1].value`; the processor logs `rule_invalid` and skips that rule.

Example, "Anna: critical from payments-api, SMS 08:00-20:00":

```yaml
id: payments-critical-daytime
team: payments
when:
  all:
    - { field: normalized.source, op: eq, value: payments-api }
    - { field: normalized.severity, op: severity_gte, value: critical }
    - field: normalized.occurred_at
      op: time_between
      value: { range: "08:00-20:00", timezone: Europe/Warsaw }
route: { channels: [sms] }
present:
  title: "Critical on payments-api"
```

### `schema_profile`
- **Directory:** `config/schemas/<id>.yaml` (`.yaml`, `.yml`)
- **JSON Schema:** [`config.SchemaProfile.schema.json`](../contracts/schemas/config.SchemaProfile.schema.json)
- Recognises an event shape via `match` and maps **normalized fields** (`type`, `source`, `severity`, `occurred_at`, `entity`), **fingerprint** paths, and an optional `resolution` condition; never filters events. When several **schema profiles** match, the highest `priority` wins, and unmatched events fall back to the **generic profile** (`config/schemas/generic.yaml`).

### `recipient`
- **Directory:** `config/recipients/<id>.yaml` (`.yaml`, `.yml`)
- **JSON Schema:** [`config.Recipient.schema.json`](../contracts/schemas/config.Recipient.schema.json)
- Defines an alert **recipient** with `display_name`, **team** memberships, **contacts** (`email`, `sms`, `phone`), and ordered **channel preferences**. The first matching **channel preference** selects **channels** during **working hours** (default timezone `Europe/Warsaw`) and `otherwise` channels outside them.

### `team`
- **Directory:** `config/teams/<id>.yaml` (`.yaml`, `.yml`)
- **JSON Schema:** [`config.Team.schema.json`](../contracts/schemas/config.Team.schema.json)
- Groups **recipients** that own **rules** and **runbooks**, and populates the UI team picker. Lists the static `on_call` **recipient** IDs who receive **alerts** routed to the **team**.

### `channel`
- **Directory:** `config/channels/<id>.yaml` (`.yaml`, `.yml`)
- **JSON Schema:** [`config.ChannelConfig.schema.json`](../contracts/schemas/config.ChannelConfig.schema.json)
- Configures a delivery plugin instance for a **channel type** (`ui`, `email`, `sms`, `phone`, `webhook`), with plugin `settings`, `retry` backoff, `runbook_presentation` (`full`, `link`, or `none`), and an optional **fallback channel** (`fallback_channel_id`) used when a **delivery** is dead-lettered.

### `action`
- **Directory:** `config/actions/<id>.yaml` (`.yaml`, `.yml`)
- **JSON Schema:** [`config.ActionConfig.schema.json`](../contracts/schemas/config.ActionConfig.schema.json)
- Configures an executable operation invoked by **runbook steps**, where `type` selects the action plugin (for example `http_get`, `webhook`, `retry_workflow`, `restart_service`, `open_ticket`, `escalate`; `webhook` actions need no code). Sets `approval` (`none` or `required`), `timeout`, typed `params`, and plugin `settings`.

### `source`
- **Directory:** `config/sources/<id>.yaml` (`.yaml`, `.yml`)
- **JSON Schema:** [`config.SourceConfig.schema.json`](../contracts/schemas/config.SourceConfig.schema.json)
- Configures an event input of a **source type** (`webhook`, `alertmanager`, or `log_tail`) with optional owning `team`, `enabled` flag, and plugin-specific `settings`. HTTP sources accept events at `POST /api/v1/ingest/<id>` (and `/batch`), which `services/ingest` wraps into an **event envelope**.

### `runbook`
- **Directory:** `config/runbooks/<id>.<ext>` (`.yaml`, `.yml`, `.md`, or `.txt`)
- **JSON Schema:** [`config.RunbookYamlDocument.schema.json`](../contracts/schemas/config.RunbookYamlDocument.schema.json) (YAML file input) · [`Runbook.schema.json`](../contracts/schemas/Runbook.schema.json) (stored normalized document)
- Holds response instructions in one of three **runbook formats** (`yaml`, `markdown`, or `text`), normalized on load into ordered **runbook steps** (`text`, `check`, `action`) while keeping the original `source` text. Loader reads sibling **actions** from `config/actions/` to resolve action references and **approval** defaults.

## Hot reload

Configuration is stored in the Postgres `config_documents` table and hot-reloaded via `packages/alerting_core/alerting_core/config/`.

### Saving through the UI or API

- Write endpoints in `services/api` (for **rules**, **schema profiles**, **recipient** **channel preferences**, **runbooks**, and accepted **fix proposals**) call `save_config_document()` (or `save_runbook()`, which wraps it) in `alerting_core.config.store`.
- `save_config_document()` validates the payload against the kind's Pydantic model, renders canonical JSON (`document`, defaults omitted, aliases applied) and canonical YAML (`yaml`), atomically upserts the row in `config_documents` with an incremented `version`, and calls `publish_config_changed()`.
- `publish_config_changed()` emits a `ConfigChangedEvent` to two Redis pub/sub channels: `config.changed` (consumed by services) and `broadcast` (relayed to UI SSE clients).
- UI/API saves write to Postgres only; they do not modify files under `config/`.

### Startup sync and editing files on disk

- **Startup sync (`sync_config_files`):** `services/processor` and `services/runbook_runner` register `runbook` and call `sync_config_files()` at startup. A file on disk is upserted into `config_documents` only when no row exists yet, or when its canonical `document` differs from the stored row **and** the file's `mtime` is newer than `config_documents.updated_at`. Compare and upsert execute in a single SQL statement so concurrent replicas cannot race; otherwise the database copy (from UI/API edits) wins. Note that touching files (for example via `git checkout`) refreshes `mtime` and causes disk files to overwrite older UI/API edits on the next sync.
- **File watcher (`watch_config_directory`):** `alerting_core.config.watcher` implements `watch_config_directory()` (using `watchfiles.awatch` with `force_polling=True` by default because Docker Desktop bind mounts drop inotify events) and `handle_config_file_change()`. When running in a single process, it validates added or modified files, skips invalid files and no-op saves whose canonical document already matches Postgres, saves changes through `save_config_document()` as actor `system:config-watcher`, and ignores file deletions (use the API to delete documents).
- **Current service wiring:** `watch_config_directory()` is implemented and tested in `alerting_core`, but is not started by `services/api/main.py` in the current stack. As a result, UI/API edits hot-reload immediately, while on-disk edits under `config/` are synced when `processor` or `runbook_runner` starts (provided the file's `mtime` is newer than `updated_at`). In addition, `services/ingest` loads `config/sources/*.yaml` once at startup via `load_sources()`, so changes to **sources** require restarting `ingest`.

### How services apply reloads (`ConfigRegistry`)

- `services/api`, `services/processor`, `services/delivery`, and `services/runbook_runner` each run an `alerting_core.config.ConfigRegistry` subscribed to Redis `config.changed`.
- On each `config.changed` message, `reload()` queries `config_documents`, validates every row for registered kinds, and replaces `registry.snapshot` with a new immutable `ConfigSnapshot` in one assignment before invoking any `on_reload` callbacks.
- Concurrent reload requests are serialized and coalesced under an async lock so a burst triggers at most two reloads. If a single row fails validation, that `(kind, id)` keeps its previous valid model (or is omitted if new) while all other documents still swap; if Postgres is unavailable, the previous snapshot is preserved.
- A background reconciliation loop checks `(max(updated_at), count(*))` every 30 seconds (`reconcile_interval=30.0`), and the Redis listener reconnects with exponential backoff (up to 5 s) and triggers a reload on reconnect, catching any `config.changed` message lost during a Redis outage.
