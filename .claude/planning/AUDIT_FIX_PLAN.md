# Audit fix plan (backend and infra)

Source: backend audit of 2026-11-21 (four read-only reviewers plus orchestrator spot checks). Task IDs
continue `.claude/planning/IMPLEMENTATION_PLAN.md` (last used: S-03, A-34, B-26). Definition of done follows
`CLAUDE.md` (tests, lint, smoke `--gate 14h`, no contract drift, one CHANGELOG line, only listed files
changed). One branch per task.

**Ownership override for this plan:** Person A owns every non-UI path, including the paths `OWNERSHIP.md`
gives to B (`services/api/**`, `services/runbook_runner/**`, `alerting_core/runbooks/**`,
`alerting_core/llm/**`, `plugins/actions/**`, `plugins/runbook_formats/**`, `config/{runbooks,actions}/**`,
`README.md`, `docs/demo.md`). Person B owns only `web/**`. The LLM is reachable through the local `.env`
(`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_ALLOWED_HOSTS`); `.env` is gitignored and never committed or printed.

## 1. Findings → tasks

| # | Finding (verified ✔ / reported by reviewer ○) | Criterion hit | Task(s) |
|---|---|---|---|
| 1 | ✔ README headlines 250 msg/s, A-24 measured ≥ 350; `git clone <repo>` placeholder; 55 of 81 raw result files untracked; newest 500 msg/s run cited nowhere | Throughput, Level, DevEx | A-35, A-42 |
| 2 | ✔ Email never gets runbook steps: `runbook_step_texts` (`runbooks/rendering.py:86`) has no caller, so `plugins/channels/email.py:65` is dead | 2.6, Level | A-36 |
| 3 | ✔ Ingest loads sources once (`services/ingest/main.py:241`); a new source needs a restart | **Flexibility** | A-37 |
| 4 | ○ No ordinal severity ("WARN or above" is a lexical `gt`); no time-of-day predicate; bad regex/glob accepted on save and silently skipped (`processor/evaluation.py:66`) | **Flexibility** | S-04, A-38, A-43, B-28, B-29 |
| 5 | ✔ No API route runs a manual runbook step (only `/normalize`, ack, resolve, approval decision exist) | 2.6 | S-04, A-44, B-27 |
| 6 | ○ Markdown keyword actions get empty params (`markdown_format.py:38`), so retry/restart/escalate fail | 2.6 | A-45 |
| 7 | ○ Free-text runbooks loaded from files never reach the LLM (`runbooks/store.py:66`); LLM steps are not checked against action params or approval policy (`text_format.py:16-47`) | 2.6, safety | A-46, B-30 |
| 8 | ○ Approval after auto-resolve still runs the action (`routers/approvals.py:126`) | 2.6, safety | A-47 |
| 9 | ✔ `trim_events` does `XTRIM MINID now-2h` regardless of consumer lag (`processor/main.py:36-45`); a > 2 h processor outage loses events | Scalability, "zero lost" | A-39 |
| 10 | ○ Reconciler re-publishes only `pending` deliveries, not `runbook_job` outbox rows (`outbox_relay/reconcile.py:16`) | Scalability, "zero lost" | A-40 |
| 11 | ○ `api`/`ingest` publish fixed host ports → `--scale` fails; throughput plateaus ~420 msg/s regardless of processor count | Scalability, Throughput | A-41 (cut-1) |
| 12 | ✔ No video or slides | Presentation | A-48, D-04 |

## 2. Schedule

```
Wave 0 (A, ~20 min)  S-04 contract v1.1 ──▶ regenerates web/src/api/schema.gen.ts (B pulls)
Wave 1  A: A-35 · A-36 · A-37 · A-39 · A-47 · A-45        B: (waits for S-04) UI polish backlog
Wave 2  A: A-38 · A-40 · A-44 · A-46 · A-42               B: B-27 (after A-44) · B-30 (after A-46)
Wave 3  A: A-43 (after A-38) · A-41 (stretch) · A-48      B: B-28 (after A-43) · B-29 (after A-38)
Gate    smoke --gate 14h green · D-03 re-rehearsal · D-04 video (both)
```

A's tasks in the same wave run in parallel only when their `Files` lists do not overlap: A-44 and A-47
both touch `services/runbook_runner/runner.py`, so A-47 lands first (wave 1) and A-44 rebases.

| ID | Title | Owner | Tier / agent | Est. | Depends on | Cut |
|---|---|---|---|---|---|---|
| S-04 | Contract v1.1: rule operators, validation errors, manual step run route | A | opus / orchestrator | 20 min | — | keep |
| A-35 | Commit load-test evidence, refresh results doc, fix compose comment | A | haiku / scaffolder | 15 min | — | keep |
| A-36 | Send numbered runbook steps to full-presentation channels (email) | A | sonnet / backend-engineer | 30 min | — | keep |
| A-37 | Hot-reload sources in ingest | A | sonnet / backend-engineer | 45 min | — | keep |
| A-38 | Implement `severity_gte`, `time_between` and `validate_rule` | A | sonnet / backend-engineer | 1 h | S-04 | keep |
| A-39 | Trim `events` only below the slowest consumer group | A | opus / orchestrator | 25 min | — | keep |
| A-40 | Reconcile stuck `runbook_job` outbox rows | A | opus / orchestrator | 30 min | — | cut-2 |
| A-41 | Scale `api`/`ingest` behind a proxy; rerun saturation | A | opus / orchestrator | 1.5 h | A-35 | cut-1 |
| A-42 | README: repo URL, current load numbers, limitations | A | haiku / docs-writer | 15 min | A-35 | keep |
| A-43 | Reject invalid rules on save with field-level errors (API) | A | sonnet / backend-engineer | 20 min | A-38 | keep |
| A-44 | Run a manual runbook step (API route + runner) | A | sonnet / backend-engineer | 1.2 h | S-04, A-47 | keep |
| A-45 | Markdown action steps with inline params | A | sonnet / plugin-author | 45 min | — | keep |
| A-46 | LLM-normalize file free-text runbooks; guard LLM steps | A | sonnet / plugin-author | 1 h | — | keep |
| A-47 | Refuse approvals and action runs on resolved alerts | A | sonnet / backend-engineer | 30 min | — | keep |
| A-48 | Update `docs/demo.md` with the new scenes | A | haiku / docs-writer | 20 min | keep tasks | keep |
| A-49 | Normalize free-text runbooks with the LLM in one service only | A | sonnet / backend-engineer | 30 min | A-46 | cut-2 |
| B-27 | Wire the alert-detail Run button to the manual step route | B | sonnet / frontend-engineer | 30 min | A-44 | keep |
| B-28 | Show rule validation errors inline in the rule editor | B | sonnet / frontend-engineer | 30 min | A-43 | keep |
| B-29 | Rule editor support for `severity_gte` and `time_between` | B | sonnet / frontend-engineer | 30 min | S-04, A-38 | keep |
| B-30 | Runbooks tab: mark LLM steps and forced approvals | B | sonnet / frontend-engineer | 20 min | A-46 | cut-2 |
| D-04 | Record and submit the video (≤ 5 min, Lockbox, repo link) | both | humans | 1.5 h | A-48 | keep |

Totals: Person A ≈ 7.5 h keep (+1.5 h stretch), split across parallel subagents; Person B ≈ 2 h plus the
video.

## 3. Task details

### Contract (A, orchestrator)

**S-04 Contract v1.1: rule operators, validation errors, manual step run route** — opus, orchestrator.
_Done: the step-run route (`runRunbookStep`, `StepRunRequest`) and `ErrorResponse.details: ConfigValidationError[]` already existed in v1, and `web/src/components/runbooks/useStepRun.ts` already calls the route. S-04 only added the two operators (`time_between` value: `"HH:MM-HH:MM"` UTC or `{range, timezone}`; a `timezone` field on the leaf was rejected because it breaks web typecheck), 404/409/422 on the step-run route and 422 on preview. A-43 reuses `ConfigValidationError`; A-44 implements the existing route; B-27 shrinks to checking the existing button._
Files: `contracts/alerting_contracts/config.py`, `contracts/alerting_contracts/api.py`,
`contracts/openapi.yaml`, generated `contracts/schemas/**`, `web/src/api/schema.gen.ts` (generated),
`docs/glossary.md`.
- AC:
  - `ConditionOperator` gains `severity_gte` and `time_between`. `ConditionLeaf.value` accepts a
    `TimeWindow` model `{start: "HH:MM", end: "HH:MM", timezone: str}` for `time_between` (window may wrap
    midnight). Glossary defines both and the severity rank `debug < info < warning < error < critical`
    with aliases `WARN→warning`, `ERR→error`, `FATAL/CRIT→critical` (case-insensitive).
  - `api.py` adds `ManualStepRunRequest {actor: str}` and `RuleValidationError {path: str, message: str}`;
    OpenAPI adds `POST /api/v1/alerts/{alert_id}/runbook/steps/{step_index}/run` → `ActionRun` (202),
    409 when the alert is resolved or the step already has a non-failed run, 422 when the step has no
    action; `PUT /api/v1/rules/{rule_id}` and the preview route document 422 with
    `list[RuleValidationError]`.
  - No change to `RunbookJob`: the run reuses `job_type: execute_action_run` with `action_run_id`.
- Verify: `uv run python scripts/generate_contracts.py --check` · `uv run pytest contracts -q` · commit
  `feat(contracts): v1.1 rule operators and manual step run`; tell B to pull the regenerated TS types.

### Track A: ingest, processor, delivery, infra

**A-35 Commit load-test evidence, refresh results doc, fix compose comment** — haiku, scaffolder. Files:
`loadtest/results/**`, `docs/load-test-results.md`, `compose.yaml` (header comment only), `.gitignore`
(only to keep `profiles/load.log` out).
- AC: every JSON/CSV referenced by `docs/load-test-results.md` plus the newest steady/saturation/cpu-bench
  runs is tracked; `profiles/load.log` is not. The doc gains a "500 msg/s" row from
  `steady-20261121T020925.json` (achieved rate, p50/p99, lost) and a summary at the top stating the current
  max sustainable rate (≥ 350 msg/s, A-24) and the ~420 msg/s plateau. The `compose.yaml:1-3` comment
  matches reality (`web` has no profile).
- Verify: every `loadtest/results/...` path in the doc exists and is tracked
  (`git ls-files --error-unmatch <path>`).

**A-36 Send numbered runbook steps to full-presentation channels (email)** — sonnet, backend-engineer.
Files: `services/processor/deliveries.py`, processor tests.
- AC: when an alert has a rendered runbook, every `DeliveryJob`'s `NotificationContent.runbook_steps` is
  `runbook_step_texts(rendered)`. Email with `runbook_presentation: full` lists numbered steps with event
  values filled in; SMS/phone stay link-only. Rendering happens once per alert, not per delivery; no LLM
  call.
- Verify: unit test on the settlements fixture asserts step text contains the workflow id ·
  `make smoke GATE=14h` · Mailpit message shows the steps · **code-reviewer** (hot path).

**A-37 Hot-reload sources in ingest** — sonnet, backend-engineer. Files: `services/ingest/main.py`,
`services/ingest/sources.py`, ingest tests, `plugins/sources/README.md`.
- AC: ingest reads `SourceConfig` from `ConfigRegistry` (same pattern as the processor) and reloads on
  `config.changed`. A new `config/sources/<id>.yaml` of an existing type is accepted by
  `POST /api/v1/ingest/<id>` within 2 s without a restart; a deleted source returns 404. Log-tail sources
  start/stop their tail task on reload (a changed path restarts that tail only). README states "new
  source of an existing type = YAML only".
- Verify: unit test with a fake registry (add/remove source) · manual: copy `generic-webhook.yaml` to
  `judges.yaml`, POST a fixture to `/api/v1/ingest/judges` → 202 with no container restart ·
  **code-reviewer** (hot path).

**A-38 Implement `severity_gte`, `time_between` and `validate_rule`** — sonnet, backend-engineer. Files:
`packages/alerting_core/alerting_core/rules/conditions.py`, `packages/alerting_core/tests/rules/**`,
`config/rules/pricing-stale-feed.yaml`, `config/README.md`.
- AC:
  - `severity_gte` ranks both sides with the glossary table; an unknown value → no match (never raises).
  - `time_between` compares the event time (`normalized.timestamp`, falling back to receive time) in the
    given timezone; wrap-around windows (`20:00–08:00`) work.
  - `validate_rule(rule) -> list[RuleValidationError]` compiles every regex (existing ReDoS guard), glob,
    `in` list, `TimeWindow` and severity literal and reports dot-path locations (`when.all[1].value`).
    The processor still skips invalid rules but logs `rule_invalid` once per version.
  - `pricing-stale-feed.yaml` uses `severity_gte: warning`; `config/README.md` documents both operators,
    with the Appendix A "Anna 08:00–20:00" example written as a rule.
- Verify: `uv run pytest packages/alerting_core/tests/rules -q` (`ERROR ≥ WARN`, `info < warning`,
  wrap-around window, timezone, invalid regex reported) · `make smoke GATE=14h` · **code-reviewer**.

**A-39 Trim `events` only below the slowest consumer group** — opus, orchestrator. Files:
`services/processor/main.py`, processor tests.
- AC: trim target = the minimum of `now − 2 h`, the oldest pending id of every group on `events` and every
  group's last-delivered-id (`XINFO GROUPS`, `XPENDING … - + 1`). If any read fails, skip the round.
- Verify: unit test with a fake Redis where the pending id < now − 2 h → `xtrim` gets that id ·
  `loadtest/lost_jobs_test.sh` still 0 lost.

**A-40 Reconcile stuck `runbook_job` outbox rows** — opus, orchestrator. Files:
`services/outbox_relay/reconcile.py`, outbox-relay tests.
- AC: the reconciler also re-publishes `runbook_job` outbox rows relayed more than N s ago whose action
  run is still `pending`/`queued`; the runner's `(alert_id, step_index, attempt)` idempotency makes a
  duplicate harmless.
- Verify: unit test (row relayed, run still pending → re-published once) · `loadtest/redis_kill_test.sh`
  0 lost runbook jobs.

**A-41 Scale `api`/`ingest` behind a proxy; rerun saturation (stretch)** — opus, orchestrator. Files:
`compose.yaml`, `deploy/nginx/nginx.conf` (new), `loadtest/results/**`, `docs/load-test-results.md`.
- AC: nginx owns host ports 8000/8001 and proxies to `api`/`ingest` (SSE: `proxy_buffering off`, long
  read timeout); `docker compose up -d --scale ingest=3 --scale api=2 --scale processor=4` works. A
  saturation rerun with `ingest=3, processor=4, outbox-relay=2` is recorded.
- Verify: `make smoke GATE=14h` with the scaled stack ·
  `uv run python loadtest/scenarios.py saturation --replicas 4 --rates 350,500,700`.

### Track A: API, runbooks, LLM, docs (moved from B)

**A-42 README: repo URL, current load numbers, limitations** — haiku, docs-writer. Files: `README.md`.
- AC: real repo URL in Quickstart; the load-test table and saturation sentence use A-35's numbers;
  "Known limitations" lists the fixed host ports of `api`/`ingest` (dropped if A-41 lands) and the trim
  rule from A-39; first-build time measured once on a clean clone and stated.
- Verify: every number matches `docs/load-test-results.md`; links resolve.

**A-43 Reject invalid rules on save with field-level errors (API)** — sonnet, backend-engineer. Files:
`services/api/routers/rules.py`, api tests.
- AC: `PUT /api/v1/rules/{id}` and the preview route call `validate_rule` after Pydantic validation and
  return 422 with `list[RuleValidationError]` before storing. No duplicate validation logic in the API.
- Verify: API test with `regex: "("` → 422 with a `when…value` path · smoke 11h rule-reload check green.

**A-44 Run a manual runbook step (API route + runner)** — sonnet, backend-engineer. Files:
`services/api/routers/runbook_runs.py` (new, registered in `services/api/main.py`),
`services/runbook_runner/runner.py`, `services/runbook_runner/store.py`, their tests.
- AC: the S-04 route, in one transaction, checks the alert is not resolved and the step has an action,
  inserts an `action_runs` row (`pending`, actor from the body), writes the audit entry
  `runbook_step_run_requested` and calls `enqueue_runbook_job(RunbookJob(job_type=execute_action_run,
  action_run_id=…))`. A step with `approval: required` creates an approval request instead. The runner
  executes manual `execute_action_run` jobs (today skipped at `runner.py:148`) and publishes the run
  status over SSE.
- Verify: API test (202, row + outbox row; 409 on resolved) · runner test (runs once, idempotent on
  redelivery) · `curl` the route for the Markdown "open ticket" step → `succeeded` in the audit trail ·
  **code-reviewer** (runbook runner).

**A-45 Markdown action steps with inline params** — sonnet, plugin-author. Files:
`plugins/runbook_formats/markdown_format.py`, `plugins/runbook_formats/tests/**`,
`plugins/runbook_formats/README.md`, `config/runbooks/trade-limit-breach.md`.
- AC: a list item may end with an inline action such as `` `retry_workflow workflowId={{workflowId}}` ``
  or `` `escalate team=counterparty-support approval=required` ``; `key=value` pairs (quoted values
  allowed) become step params, templated at render time. A keyword step without required params becomes a
  manual text step, not a failing action. "(needs approval …)" in prose sets `approval: required`
  (Appendix B step 2). The format README shows the syntax.
- Verify: tests on the Appendix B Markdown runbook (step 2 requires approval; no step fails on missing
  params) · `make smoke GATE=14h`.

**A-46 LLM-normalize file free-text runbooks; guard LLM steps** — sonnet, plugin-author. Files:
`packages/alerting_core/alerting_core/runbooks/store.py`, `plugins/runbook_formats/text_format.py`, their
tests, `config/runbooks/pricing-stale-feed.txt` (wording only, if needed).
- AC: a `text` runbook synced from files is normalized once when the LLM is reachable and cached by
  content hash (`llm/cache.py`); unreachable → the single-text-step fallback, retried on the next sync.
  Never on the hot path. Each LLM step is validated: the action exists and required params are present
  (else it becomes a manual text step), and `approval: required` is forced for any action whose
  `ActionConfig` is not `approval: none`. `redact_secrets` runs before the call; the host is in
  `LLM_ALLOWED_HOSTS`.
- Verify: tests with a fake LLM — (a) valid restart step → kept with approval, (b) unknown action → text
  step, (c) timeout → fallback · `uv run python scripts/check_llm.py` against the `.env` endpoint ·
  Appendix B free text yields restart (approval) → wait → escalate · `scripts/eval_runbook_llm.py` score
  not lower than `docs/llm-eval-results.md`.

**A-47 Refuse approvals and action runs on resolved alerts** — sonnet, backend-engineer. Files:
`services/api/routers/approvals.py`, `services/api/approvals_store.py`,
`services/api/routers/phone_simulator.py`, `services/runbook_runner/runner.py`, tests.
- AC: deciding an approval whose alert is `resolved` returns 409 and expires the request (audit
  `approval_expired`); the runner re-checks the alert status before running any action and marks the run
  `cancelled` when resolved; an SMS `APPROVE <code>` on a resolved alert answers "Alert already
  resolved".
- Verify: API test (resolve → approve → 409) · runner test (resolved → no plugin call) · smoke 14h green.

**A-48 Update `docs/demo.md` with the new scenes** — haiku, docs-writer. Files: `docs/demo.md`.
- AC: the 5-minute script adds: a new source by YAML only (A-37), "WARN or above" and Anna's hours as rule
  operators (A-38), email with runbook steps (A-36), a Markdown step Run (A-44/A-45), free text → LLM steps
  with forced approval (A-46), current load numbers.
- Verify: `uv run python scripts/demo_rehearsal.py` passes.

**A-49 Normalize free-text runbooks with the LLM in one service only** — sonnet, backend-engineer. Files:
`packages/alerting_core/alerting_core/config/store.py`, `services/api/main.py`, the `main.py` of `ingest`,
`processor`, `runbook-runner` (only the sync call), their tests.
- Why: after A-46 every service runs `sync_config_files` at startup with the LLM flag on. Only cache hits reach
  the LLM, but `llm_cache_hit` lines in the `processor` logs read as "the hot path touches the LLM" in a demo.
- AC: only `api` syncs with `normalize_text_with_llm=True` and stores the normalized runbook in
  `config_documents`; `processor`, `ingest` and `runbook-runner` sync with the flag off and read the stored
  steps from the registry. If `api` is not up yet, the others keep the parser fallback and pick up the LLM steps
  on the next `config.changed`. No `alerting_core.llm` log line from `processor`/`ingest`/`runbook-runner`.
- Verify: unit test (flag per service) · `docker compose logs processor ingest runbook-runner | grep -c llm_` = 0
  after `docker compose up -d --build` · the pricing runbook still shows `normalizer: llm` in the Runbooks tab.

### Track B: UI only

**B-27 Wire the alert-detail Run button to the manual step route** — sonnet, frontend-engineer. Files:
the alert-detail runbook component under `web/src/components/alerts/` and its API hook.
- AC: Run calls `POST /api/v1/alerts/{id}/runbook/steps/{n}/run` with the selected team member as actor;
  disabled for resolved alerts and for steps with a non-failed run; shows `pending → running →
  succeeded/failed` from SSE; a step needing approval shows "Waiting for approval".
- Verify: `cd web && npm run lint && npm run typecheck` · manual click-through on the trade-limit-breach
  alert.

**B-28 Show rule validation errors inline in the rule editor** — sonnet, frontend-engineer. Files:
`web/src/components/rules/**`.
- AC: a 422 with `RuleValidationError[]` from save or preview marks the YAML line for each `path` and lists
  the messages; Save stays disabled until fixed.
- Verify: lint + typecheck · enter `regex: "("` → inline error, nothing saved.

**B-29 Rule editor support for `severity_gte` and `time_between`** — sonnet, frontend-engineer. Files:
`web/src/components/rules/**`.
- AC: both operators appear in operator autocomplete/hints with a one-line example each (`severity_gte:
  warning`, `time_between: {start: "08:00", end: "20:00", timezone: Europe/Warsaw}`).
- Verify: lint + typecheck · preview of the updated pricing rule matches WARN and ERROR lines.

**B-30 Runbooks tab: mark LLM steps and forced approvals** — sonnet, frontend-engineer. Files:
`web/src/components/runbooks/**`.
- AC: steps produced by the LLM carry an "AI proposal" badge; steps whose approval was forced by the guard
  show "Approval required".
- Verify: lint + typecheck · the pricing free-text runbook shows both badges.

## 4. Acceptance gate for this plan

- `uv run ruff check . && uv run ruff format --check .` · `uv run pytest -q` · `make smoke GATE=14h`
- `uv run python scripts/generate_contracts.py --check` · `cd web && npm run lint && npm run typecheck`
- `uv run pytest -m integration tests/integration -q` (channel-down and worker-kill still 0 lost)
- One CHANGELOG line per task (`- A-36 processor: …`), Conventional Commits with `Task: <ID>`.
