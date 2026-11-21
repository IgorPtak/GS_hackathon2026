# Domain glossary

**One concept = one name everywhere** (Python, TypeScript, SQL, YAML, API, UI, logs). If a name is
not here, add it here first (shared file, contract change rule applies after hour 1).

Casing rules derived from each canonical name:

| Context | Form | Example (`channel preference`) |
|---|---|---|
| Python class / TS type | `PascalCase` | `ChannelPreference` |
| Python/TS field, SQL column, YAML key, JSON/API field, log field | `snake_case` | `channel_preferences` |
| SQL table | plural `snake_case` | `channel_preferences` |
| Redis key / stream / pub/sub channel | `kebab-case` segments separated by `:` or `.` | `deliveries`, `alerts.team.<team_id>` |
| URL path | plural `kebab-case` | `/api/v1/channel-preferences` |
| UI label | sentence case | "Channel preferences" |

JSON on the wire is `snake_case` (no aliasing between Python and TypeScript).

## Terms

| Canonical name | Polish in `docs/plan.md` | Definition | Where in code |
|---|---|---|---|
| **event** | zdarzenie | One raw message received from a source, stored unchanged in the `events` stream. | `EventEnvelope` (contracts), stream `events`, field `payload` |
| **event envelope** | — | Wrapper around a raw event with ingest metadata (`event_id`, `source_id`, `received_at`, `sent_at`). | `alerting_contracts.events.EventEnvelope` |
| **source** | źródło | A configured input that produces events: `webhook`, `alertmanager`, `log_tail`. | `config/sources/*.yaml`, `plugins/sources/`, `SourceConfig`, UI "Sources" |
| **source type** | typ źródła | The plugin kind of a source (`webhook`, `alertmanager`, `log_tail`). | `SourceConfig.type`, `SourcePlugin.type` |
| **schema profile** | profil schematu | YAML that recognises an event shape and maps its shared fields; does not filter. | `config/schemas/*.yaml`, `SchemaProfile`, table `config_documents` (kind `schema_profile`), UI "Schema profiles" |
| **generic profile** | profil `generic` | Fallback schema profile with heuristics (`severity`, `level`, `labels.severity`) for events no profile matches. | `config/schemas/generic.yaml`, id `generic` |
| **field mapping** | mapowanie | How one normalized field is extracted (path, constant, format, value map). | `FieldMapping` |
| **normalized fields** | pola znormalizowane / wspólne | Fields shared by all events after profile mapping: `type`, `source`, `severity`, `occurred_at`, `entity`, `fingerprint`, `is_resolution`. | `NormalizedFields`, rule paths prefixed `normalized.` |
| **severity** | severity | Ordered level: `debug` < `info` < `warning` < `error` < `critical`. | `Severity` enum |
| **fingerprint** | fingerprint | Stable hash of selected event fields; identical fingerprint = identical event for dedup. | `NormalizedFields.fingerprint`, `Alert.fingerprint` |
| **rule** | reguła | Condition + route + presentation + dedup/group/throttle + optional runbook, owned by a team. | `config/rules/*.yaml`, `Rule`, table `config_documents` (kind `rule`), UI "Rules" |
| **condition** | warunek | Tree of `all` / `any` / `not` / leaf `{field, op, value}` evaluated on raw event JSON and normalized fields. | `Condition`, `alerting_core.rules.evaluate_condition` |
| **operator** | operator | Leaf comparison: `eq ne gt gte lt lte in glob regex exists severity_gte time_between`. `severity_gte` ranks by severity order (aliases `WARN`→`warning`, `ERR`→`error`, `FATAL`/`CRIT`→`critical`, case-insensitive); `time_between` takes `HH:MM-HH:MM` (UTC, may wrap midnight) or `{range: HH:MM-HH:MM, timezone: <IANA>}`. | `ConditionOperator` |
| **field path** | ścieżka | Dot path into the raw event (`payload.notional`) or normalized fields (`normalized.severity`). | `alerting_core.rules.resolve_field_path` |
| **route** | routing | Which recipients and channels a rule's alerts go to. | `Rule.route`, `Route` |
| **presentation** | prezentacja | Title/body templates, listed fields and color for a rule's alerts. | `Rule.present`, `Presentation` |
| **template** | szablon | `{{path}}` placeholders filled from the event/alert. | `alerting_core.templating.render_template` |
| **dedup window** | okno dedup | Time during which events with the same rule + fingerprint increment one alert's `count`. Fixed from the first event; when it expires while that alert is still open, the next event re-arms the window and keeps folding into the same alert. | `Rule.dedup.window`, Redis `dedup:<rule_id>:<fingerprint>` |
| **group window** | okno grupowania (`group.every`) | Time during which *different* events with the same rule + group key are buffered and then flushed as one group summary alert. | `Rule.group.window`, Redis `group-buffer:<rule_id>:<group_key>` |
| **group key** | klucz grupy | Values of `Rule.group.by` paths joined, e.g. the instrument. | `Alert.group_key` |
| **throttle** | throttling / limit na odbiorcę | Max deliveries per recipient per rule per period; excess is suppressed and audited. | `Rule.throttle`, Redis `throttle:<rule_id>:<recipient_id>` |
| **alert** | alert | Internal record created from one or more matching events; has a status, count and audit. | `Alert`, table `alerts`, UI "Alerts" |
| **alert status** | status | `open` → `acknowledged` → `resolved` (any → `resolved`). | `AlertStatus` |
| **auto-resolve** | auto-zamykanie | Resolving an alert from a source resolution event or after silence. | `Rule.auto_resolve`, `Alert.resolution_reason` |
| **recipient** | odbiorca (osoba) | A person with contacts and channel preferences. | `config/recipients/*.yaml`, `Recipient`, table `config_documents` (kind `recipient`) |
| **team** | zespół | Group of recipients that owns rules and runbooks; selected in the UI dropdown. | `config/teams/*.yaml`, `Team`, table `config_documents` (kind `team`), UI team picker |
| **contact** | kontakt | Address of a recipient on a channel type (email address, phone number). | `Recipient.contacts` |
| **channel** | kanał | A configured delivery plugin instance: `ui`, `email`, `sms`, `phone`, `webhook`. | `config/channels/*.yaml`, `ChannelConfig`, `plugins/channels/`, `ChannelPlugin` |
| **channel type** | typ kanału | Plugin kind of a channel. | `ChannelType` |
| **fallback channel** | kanał zapasowy | Channel used when a delivery is dead-lettered on its primary channel. | `ChannelConfig.fallback_channel_id` |
| **channel preference** | preferencja kanałów | Recipient rule: for alerts matching severity/source, use these channels during working hours, otherwise those. | `ChannelPreference` (inside `Recipient`), UI "Channel preferences" |
| **working hours** | godziny | Time-of-day window (`08:00-20:00`, with timezone) inside which a preference's `channels` apply. | `ChannelPreference.working_hours` |
| **on-call** | on-call / dyżur | Recipients of a team who receive alerts routed to the team. Static list (schedules are out of scope). | `Team.on_call` |
| **delivery** | dostawa | One attempt-tracked notification of one alert to one recipient on one channel. | `Delivery`, table `deliveries`, stream `deliveries` |
| **delivery status** | — | `pending` → `sent` / `failed` (retrying) → `delivered` or `dead_lettered`. | `DeliveryStatus` |
| **outbox** | outbox | Postgres table written in the same transaction as the alert; relayed to Redis streams. | table `outbox`, `OutboxEntry`, `services/outbox_relay` |
| **outbox relay** | relay | Process that moves unrelayed outbox rows to streams with `FOR UPDATE SKIP LOCKED`. | `services/outbox_relay` |
| **dead-letter queue** | DLQ / kolejka błędów | Stream for deliveries that exhausted retries (and events that failed validation). | streams `deliveries-dlq`, `events-dlq` |
| **runbook** | runbook | Response instructions for an alert type, stored in its original format plus normalized steps. | `config/runbooks/*`, `Runbook`, table `config_documents` (kind `runbook`), UI "Runbooks" |
| **runbook format** | format runbooka | `yaml`, `markdown` or `text`; each has a normalizer plugin. | `RunbookFormat`, `plugins/runbook_formats/` |
| **runbook step** | krok | One normalized instruction: `kind` = `text` / `check` / `action`. | `RunbookStep` |
| **rendered runbook** | — | Runbook steps with templates filled from one alert's values. | `RenderedRunbook` |
| **action** | akcja | A configured executable operation used by runbook steps (`http_get`, `webhook`, `retry_workflow`, …). | `config/actions/*.yaml`, `ActionConfig`, `plugins/actions/`, `ActionPlugin.execute` |
| **action run** | wykonanie akcji | One execution of a runbook step's action for an alert. | `ActionRun`, table `action_runs` |
| **approval** | zatwierdzenie / akceptacja | Human decision required before an action with `approval: required` runs. | `ApprovalRequest`, table `approval_requests`, UI "Approvals" |
| **approval code** | — | Short code included in SMS/phone messages; replying `APPROVE <code>` approves. | `ApprovalRequest.approval_code` |
| **audit entry** | wpis audytu | Who did what, when, with what outcome, on an alert. | `AuditEntry`, table `audit_entries` |
| **rule preview** | podgląd / backtest reguły | Running a draft rule over the last hour of the `events` stream to show alerts and deliveries it would produce. | `RulePreview`, `POST /api/v1/rules/preview`, UI `RulePreviewPanel` |
| **fix proposal** | propozycja poprawki ("Zaproponuj poprawkę") | Change to a rule or runbook proposed from an alert; goes to the rule owner team for a decision. | `FixProposal`, table `fix_proposals`, UI "Propose a fix" |
| **schema profile proposal** | propozycja mapowania | LLM-drafted schema profile for a sample event, approved by a human. | `SchemaProfileProposal` |
| **unknown-schema inbox** | skrzynka „nieznane schematy” | List of event shapes that matched only the generic profile. | table `unknown_schema_samples`, UI "Unknown schemas" |
| **runbook revision proposal** | plan vs fakty | Proposed new runbook version derived from what responders actually did (optional, cut-1). | `RunbookRevisionProposal` |
| **phone simulator** | zakładka „Telefon” | UI panel showing mock SMS/phone deliveries per recipient and sending replies. | UI `PhoneSimulator`, `services/mock_gateway` |
| **mock gateway** | fałszywa bramka | Local service standing in for SMS/phone providers, action targets and webhook receivers. | `services/mock_gateway` |
| **end-to-end latency** | opóźnienie end-to-end | `delivered_at − sent_at` of a generated event. | Prometheus `alert_e2e_latency_seconds` |
| **LLM client** | LLM | Single interface to an OpenAI-compatible model endpoint (local Ollama by default, allowlisted cloud host opt-in via `LLM_ALLOWED_HOSTS`) returning schema-validated JSON. | `alerting_core.llm.LlmClient` |
| **redaction** | redagowanie | Removing secret-like patterns before any LLM call. | `alerting_core.llm.redact_secrets` |

## Banned synonyms

Use the left column, never the right: alert ≠ incident/notification · recipient ≠ person/user/contact ·
acknowledged ≠ acked · group window ≠ every/batch · dedup window ≠ suppression window ·
schema profile ≠ schema/mapping/adapter · channel preference ≠ notification setting ·
fix proposal ≠ suggestion/feedback · action run ≠ execution/job.
