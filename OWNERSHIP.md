# Ownership

Each path has exactly one owner. A task (and the subagent running it) may change only paths of its
own track, as listed in its `Files` field. **Shared** paths change only through the contract rule in
`contracts/README.md` (`feat(contracts): …` commit, acknowledged by both people). If you need
something from the other track's path, ask its owner, or return `BLOCKED` when you are a subagent.

| Path | Owner | Notes |
|---|---|---|
| `contracts/**` | shared | Orchestrator edits; generated files via `scripts/generate_contracts.py` |
| `docs/glossary.md` | shared | Contract rule |
| `deploy/postgres/migrations/**` | shared | Contract rule; new migration file per change |
| `pyproject.toml`, `uv.lock` | shared | New dependencies need both people's ack |
| `CLAUDE.md`, `OWNERSHIP.md`, `.claude/agents/**`, `.claude/planning/agent-brief-template.md` | shared | Orchestrator edits |
| `.claude/planning/IMPLEMENTATION_PLAN.md` | shared | Each person ticks their own tasks; re-scoping by the orchestrator |
| `docs/CHANGELOG.md` | shared | Append-only, one line per task |
| `.claude/planning/plan.md`, `.claude/planning/task.md` | shared | Read-only after hour 0 |
| `scripts/generate_contracts.py` | shared | S-01 |
| `scripts/validate_config.py` | shared | S-03 |
| `services/ingest/**` | A | |
| `services/processor/**` | A | |
| `services/outbox_relay/**` | A | |
| `services/delivery/**` | A | |
| `services/mock_gateway/**` | A | |
| `services/api/**` | B | Calls track A library functions; never reimplements them |
| `services/runbook_runner/**` | B | |
| `packages/alerting_core/alerting_core/{settings,logging,durations,connections,metrics,streams}.py` | A | A-02 |
| `packages/alerting_core/alerting_core/config/**` | A | A-03 |
| `packages/alerting_core/alerting_core/events/**`, `event_log.py` | A | A-07, A-17 |
| `packages/alerting_core/alerting_core/rules/**`, `templating.py` | A | A-08, A-17 |
| `packages/alerting_core/alerting_core/{dedup,grouping,routing,auto_resolve,outbox}.py` | A | |
| `packages/alerting_core/alerting_core/storage/**` | A | A-09, A-19 |
| `packages/alerting_core/alerting_core/runbooks/**` | B | B-06, B-07, B-26 |
| `packages/alerting_core/alerting_core/llm/**` | B | B-08 |
| `packages/alerting_core/tests/<area>/**` | owner of `<area>` | |
| `plugins/sources/**`, `plugins/channels/**` | A | |
| `plugins/actions/**`, `plugins/runbook_formats/**` | B | |
| `config/{schemas,rules,recipients,teams,channels,sources}/**` | A | S-03 seeds everything in hour 0–1 |
| `config/{runbooks,actions}/**` | B | |
| `web/**` | B | `web/src/api/schema.gen.ts` is generated (S-01) |
| `compose.yaml`, `Makefile`, `deploy/**` (except migrations) | A | B's service entries are created in A-00; B asks A for changes |
| `loadtest/**` | A | |
| `scripts/smoke_test.py` | A | B may request checks |
| `scripts/check_llm.py` | B | |
| `tests/integration/**` | A | |
| `README.md` | B | D-01; A supplies the results table |
| `docs/demo.md`, `docs/load-test-results.md` | B, A respectively | |
| `.env.example`, `.gitignore` | shared | |
| `plugins/*/README.md`, `config/README.md`, `scripts/README.md`, other directory READMEs | owner of the directory | D-02 runs once per track |

**Hour 0–1 exception:** until the `feat(contracts): freeze v1` commit, tasks S-01–S-03, A-00 and B-00 may create
stubs in any path (for example A-00 creates the `services/api` and `services/runbook_runner` stubs).
