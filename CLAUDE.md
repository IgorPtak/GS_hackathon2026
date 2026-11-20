# CLAUDE.md

Flexible Alerting & Notification Service (18-hour hackathon, 2 people). Events from webhooks,
Alertmanager and log files go through Redis Streams (`events` → processor → Postgres outbox → relay →
`deliveries` → channel plugins). Rules, schema profiles, recipients, channels, runbooks and actions are
YAML config, hot-reloaded. A React UI shows the live feed, rule editor with preview, runbooks with
approvals and a phone simulator. An LLM (local Ollama by default, an allowlisted cloud endpoint opt-in) only proposes; humans approve.

Read before working: `docs/IMPLEMENTATION_PLAN.md` (your task) · `docs/glossary.md` (names) ·
`contracts/` (interfaces) · `OWNERSHIP.md` (what you may edit) · `docs/plan.md` (architecture, Polish).

## Commands

| What | Command |
|---|---|
| Start stack | `docker compose up -d --build` (`make up`) · scale: `docker compose up -d --scale processor=4` |
| Unit tests | `uv run pytest -q` (`make test`) · one area: `uv run pytest packages/alerting_core/tests/rules -q` |
| Integration tests | `uv run pytest -m integration tests/integration -q` (stack must be up) |
| Smoke test | `uv run python scripts/smoke_test.py --gate {3h,7h,11h,14h}` (`make smoke`) |
| Load test | `uv run python loadtest/scenarios.py steady --duration 60` (`make loadtest`) |
| Lint / format / types (Python) | `uv run ruff check . && uv run ruff format --check .` |
| Lint / types (web) | `cd web && npm run lint && npm run typecheck` |
| Contracts | `uv run python scripts/generate_contracts.py [--check]` |
| Logs | `docker compose logs -f <service>` |

## Architecture decisions (do not reopen; raise concerns as open questions)

1. Hot path (ingest → rules → dedup → delivery) makes zero LLM calls.
2. Rules evaluate raw event JSON by dot path; schema profiles only map shared fields (`normalized.*`).
3. Sources: HTTP webhook (incl. Alertmanager) and log-file tail. Redis Streams is internal, not a source.
4. Transactional outbox: alert + outbox row in one Postgres transaction; relay uses `FOR UPDATE SKIP LOCKED`; delivery is idempotent by outbox id.
5. Dedup (identical events → one alert with count) and grouping (different events → one group summary per window) are separate mechanisms.
6. Channels are plugins behind one interface: ui, email (Mailpit), mock sms/phone (phone simulator), webhook (YAML).
7. Runbooks in YAML, Markdown and free text normalize to one step model; free text uses the LLM at save time only. Actions are plugins; `approval: required` waits for a human.
8. The LLM returns schema-constrained JSON validated by Pydantic; YAML is serialized in Python; every LLM output is a proposal.
9. Never cut: rule preview, "Propose a fix", measured p50/p99 and msg/s, zero lost alerts when a channel is down.
10. No authentication; the team is picked in the UI.

## Coding conventions

- **English only** for every identifier, file, branch, commit, table/column, Redis key, YAML key, API field, log message, comment, test name and UI string. Names come from `docs/glossary.md`; banned synonyms are listed there.
- Python 3.12: type hints everywhere; Pydantic v2 at every boundary (import contract models from `alerting_contracts`, never redefine them); `ruff` + `ruff format`; `pytest` + `pytest-asyncio`; no bare `except`; structured JSON logs with `event`, `alert_id`, `rule_id`; config via env vars + YAML; no global mutable state outside explicit registries.
- TypeScript: `strict`; ESLint + Prettier; API types only from `web/src/api/schema.gen.ts` (generated, never hand-copied); small components named by what they show (`AlertFeed`, `RulePreviewPanel`, `PhoneSimulator`).
- Naming: Python modules `snake_case`, React components `PascalCase.tsx`, classes `PascalCase`, functions are verbs (`evaluate_condition`, `flush_group_window`), booleans read as questions (`is_resolved`, `requires_approval`), no abbreviations except `id`, `url`, `http`, `sse`, `llm`.
- Structure: one responsibility per module; > 300 lines per file or > 50 lines per function means split; no speculative abstraction beyond the plugin interfaces.
- Plugins: base interface + registry + one reference implementation with a test; the directory README shows how to add one in under ten lines. Adding a source, channel, action or runbook format = one new file + config.
- Comments say *why*. Public functions and every plugin interface get a docstring.
- Tests: unit tests for rule evaluation, templating, dedup, grouping, schema-profile mapping, runbook normalization; Docker integration tests for outbox → delivery and channel-down recovery.
- Git: Conventional Commits (`feat(processor): …`, `fix(web): …`), small commits, task ID in the body (`Task: A-09`).

## Definition of done

Acceptance criteria of the task met · tests added and passing · `smoke_test.py --gate <current>` green ·
lint clean · glossary names used · no contract drift (`generate_contracts.py --check`) · only files
from the task's `Files` list changed · one line in `docs/CHANGELOG.md` (`- A-09 processor worker: …`).

## Security and privacy

No secrets in the repo (`.env.example` only). Synthetic data only. The LLM client speaks the
OpenAI-compatible API; `LLM_BASE_URL` defaults to the local Ollama (`http://ollama:11434/v1`). A cloud
endpoint is opt-in via `LLM_BASE_URL` + `LLM_API_KEY` and only if its host is in `LLM_ALLOWED_HOSTS`;
the client refuses any other host. `redact_secrets` runs before every LLM call, and the hot path never
calls the LLM. Apart from that allowlisted LLM call, no code path sends events, alerts, code or config
to an external service; all other outbound URLs point at compose services or localhost.

## Model routing policy

- **Opus (orchestrator) keeps:** contracts and every change to them; cross-module design; concurrency and failure semantics (consumer groups, `XAUTOCLAIM`, outbox relay, dedup/grouping races, idempotency); integrating the two tracks; performance diagnosis after load tests; final review before each gate; anything a subagent returned `BLOCKED` on twice.
- **Sonnet:** feature work inside one module with a clear contract and acceptance criteria; plugins; UI components; LLM integration with structured output; non-trivial tests; code review.
- **Haiku:** mechanical, easy-to-check work: scaffolding, config and fixtures, docs, renames, running verification and summarizing logs.
- **Escalation:** a subagent that fails acceptance twice, needs a contract change, or needs files outside its list stops and returns `BLOCKED: <reason>`; the orchestrator re-scopes or moves the task up one tier.
- **Parallelism:** run tasks in parallel only when their `Files` lists do not overlap. Always run `verifier` after an implementation agent; run `code-reviewer` before closing any task that touches the hot path (ingest, processor, outbox relay, delivery, runbook runner, `alerting_core` rules/dedup/grouping/routing/storage).

## Delegation

Every delegation uses `docs/agent-brief-template.md`, filled from the task in the plan. Agents live in
`.claude/agents/`: `backend-engineer`, `frontend-engineer`, `plugin-author`, `test-engineer`
(sonnet), `code-reviewer` (sonnet, read-only), `scaffolder`, `docs-writer`, `verifier` (haiku;
verifier is read-only). Every agent ends with: task ID, files changed, commands run + results, open
issues, and `DONE` or `BLOCKED: <reason>`. Keep briefs minimal: point to exact files and sections,
not whole documents.
