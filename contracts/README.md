# Contracts — the only shared surface between track A and track B

## Approach

**Pydantic v2 models are the single source of truth; everything else is generated.** The backend is
Python and already validates every boundary (YAML config, stream entries, HTTP bodies, LLM output)
with Pydantic, so the models in `alerting_contracts/` are the code that actually enforces the
contract at runtime. Hand-writing JSON Schema or OpenAPI component schemas would create a second copy
that drifts. From the models we generate `schemas/*.schema.json` (editor and YAML validation),
`openapi.yaml` `components.schemas` (paths stay hand-written), and the TypeScript types in
`web/src/api/schema.gen.ts` via `openapi-typescript`. TypeScript is never hand-copied.

## Files

| Path | What it is | Edited by hand? |
|---|---|---|
| `alerting_contracts/common.py` | `Severity`, `Actor`, id/duration/template types | yes |
| `alerting_contracts/events.py` | `EventEnvelope` (stream `events`), `NormalizedFields`, `SourceType` | yes |
| `alerting_contracts/config.py` | YAML config: `SourceConfig`, `SchemaProfile`, `Condition`, `Rule`, `Recipient`, `Team`, `ChannelConfig`, `ActionConfig` | yes |
| `alerting_contracts/alerts.py` | `Alert`, `AlertStatus`, `Delivery`, `DeliveryJob`, `RunbookJob`, `OutboxEntry`, `AuditEntry` | yes |
| `alerting_contracts/runbooks.py` | `RunbookStep`, `Runbook`, `RenderedRunbook`, `ActionRun`, `ApprovalRequest` | yes |
| `alerting_contracts/proposals.py` | `FixProposal`, `SchemaProfileProposal`, `RunbookRevisionProposal` | yes |
| `alerting_contracts/api.py` | HTTP request/response bodies | yes |
| `alerting_contracts/sse.py` | `SseEvent` union (SSE + pub/sub payloads) | yes |
| `openapi.yaml` | Every HTTP endpoint (ingest + api) | paths yes, `components.schemas` **generated** |
| `schemas/*.schema.json` | JSON Schema per model | **generated** |
| `storage.md` | Redis streams, consumer groups, keys, pub/sub; Postgres tables | yes |
| `examples/` | One valid YAML per config kind; runbooks in all three formats | yes |
| `fixtures/` | Sample events and runbooks (reconstructed, see its README) | yes |

Regenerate: `uv run python scripts/generate_contracts.py` (task S-01) → writes `schemas/`,
`openapi.yaml` components, and runs `npx openapi-typescript contracts/openapi.yaml -o web/src/api/schema.gen.ts`.
`--check` mode fails when generated files are stale (run in `make lint`).

## Change rule

- **Hour 0–1:** both people edit freely; at the end of hour 1 we commit `feat(contracts): freeze v1`.
- **After hour 1:** a contract changes only through a dedicated commit `feat(contracts): <change>` that
  touches nothing outside `contracts/`, `docs/glossary.md`, generated files and
  `deploy/postgres/migrations/`. Both people acknowledge it (say "ack" in chat) before either builds on it.
- Additive changes (new optional field, new endpoint) are preferred; renames and removals need a reason
  in the commit body.
- Subagents never change contracts; they return `BLOCKED: needs contract change: <what>`.

## Conventions baked into the contract

- JSON on the wire, YAML keys and SQL columns are `snake_case`; names come from `docs/glossary.md`.
- Timestamps are ISO 8601 UTC. Ids: alerts/action runs/approvals are UUID v7, events are ULIDs,
  deliveries use the outbox `bigserial` id, config ids are slugs.
- Field paths in rules address the raw event (`payload.notional`) or normalized fields
  (`normalized.severity`). Templates use `{{path}}`; template context = raw event fields at the root,
  plus `normalized.*` and `alert.*`.
- Channel resolution per recipient: first matching `channel_preferences` entry (its `channels` inside
  `working_hours`, else `otherwise`); no match → `rule.route.channels`. The `ui` channel is delivered
  once per alert to the team, not per recipient.
