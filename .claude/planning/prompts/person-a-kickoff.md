# Kickoff prompt — Person A (track A: backend & delivery, integration owner)

> Start a fresh Claude Code session on Opus in the repository root (so `.claude/agents/` is loaded),
> then paste everything below the line.

---

You are the **orchestrator for track A** (backend & delivery) and the **integration owner** for the
whole project in an 18-hour, 2-person hackathon. My teammate runs a separate session for track B.
It is **hour 0**. Your goal is to reach the end of hour 1 with the contracts frozen and the track A
foundation moving, while doing the opus-tier work yourself and delegating everything else.

## Read first, in this order

1. `CLAUDE.md`: conventions, model routing policy, definition of done, delegation rules.
2. `.claude/planning/IMPLEMENTATION_PLAN.md`: sections 0–2, then the task details for **S-00, S-02, A-00, A-01, A-02, A-04**, and section 5 (the 3 h gate).
3. `OWNERSHIP.md`, `contracts/README.md`, `contracts/storage.md`.
4. Skim `contracts/alerting_contracts/*.py` and `docs/glossary.md`. Do not read `.claude/planning/plan.md` unless a task needs it.

## Hour 0–1 sequence

**Step 1 — Official brief (0:00–0:15).**
Check `.claude/planning/task.md`. If the official brief has been pasted under the line at the bottom, diff it
against the reconstructed requirements, judging criteria and appendices above it. Then:
- replace `contracts/fixtures/` with the official Appendix A events and Appendix B runbooks, keeping the file names;
- update `contracts/fixtures/README.md` and `contracts/examples/` where the shapes changed;
- add or adjust tasks and the traceability table (section 7 of the plan) for every requirement that is not traced;
- commit as `feat(contracts): replace reconstructed fixtures with official appendix`.

If the brief is not there, tell me in one line and continue. Do not wait.

**Step 2 — Contract review (0:15–0:35).**
Review `contracts/` for problems that would hurt track A: stream and outbox payloads, the `Alert`
fields, Redis keys, table columns, and dedup/grouping semantics. Give me **at most 8 concrete
proposed changes**, each a one-line diff idea with its reason. My teammate sends their proposals to me
too. **Only this session commits contract changes in hour 0–1**, to avoid conflicts. Apply the ones I
approve. Before 1:00, regenerate the JSON Schemas and OpenAPI components the same way as
`scripts/generate_contracts.py` will (S-01 is being built in parallel by track B; if it has landed,
use it).

**Step 3 — Dispatch A-00 (at 0:20, in parallel with step 2).**
Delegate **A-00** to the `scaffolder` agent with a brief in the exact format of
`.claude/planning/agent-brief-template.md`, filled from the plan. Add these explicit points:
- one Python image for all services (`deploy/python.Dockerfile`);
- stub services answer `/healthz` and nothing else;
- the `api` and `runbook-runner` stubs (track B) are created now under the hour-0 exception in `OWNERSHIP.md`;
- the `web` service builds from `web/Dockerfile` and starts disabled until B-00 lands (compose profile `web`);
- `ollama` runs as a compose service with a named volume;
- dependencies in `pyproject.toml` are the stack from `CLAUDE.md` only.

When it returns, run the `verifier` agent with A-00's verify commands.

**Step 4 — S-02 yourself (0:20–0:45).**
Write `deploy/postgres/migrations/0001_initial.sql` from `contracts/storage.md` (opus task: indexes,
partial indexes, the unique approval code among pending requests). Mount it in compose so it runs on
first start. Verify with the S-02 command.

**Step 5 — A-02 yourself, A-01 delegated (from 0:40, after A-00 is green).**
- Dispatch **A-01** to `test-engineer`. Only the `--gate 3h` checks need to pass now; the other gates' checks are written but are expected to fail until their features exist.
- Build **A-02** yourself. Commit `settings` and `connections` first, so A-04 can start. Then build the `StreamConsumer` with its failure semantics (ack after success, `XAUTOCLAIM` > 30 s idle, DLQ after 5 deliveries), with tests against real Redis.
- As soon as `settings` and `connections` are committed, dispatch **A-04** to `backend-engineer`.

**Step 6 — Freeze (1:00).**
When I confirm that my teammate has acknowledged, commit `feat(contracts): freeze v1`. Generated
files must be up to date. Add a line to `docs/CHANGELOG.md`.

## Rules for this session

- Opus work stays here: S-00, S-02, A-02, and later A-09, A-11, A-13, A-16, A-24 and the gate reviews. Everything else is delegated with the brief template to the agent the plan names.
- Run tasks in parallel only when their `Files` lists do not overlap. Run `verifier` after every implementation agent. Run `code-reviewer` before closing anything on the hot path.
- Never edit track B paths (`OWNERSHIP.md`), except the hour-0 stubs in A-00.
- A subagent that returns `BLOCKED` twice on the same task comes back to you: re-scope it or take it over.
- Git: small Conventional Commits with `Task: <ID>` in the body. `git pull --rebase` before every commit and push right after, because my teammate pushes to the same `main`.
- Do not stop to ask me anything that the plan, the contracts or a sensible default already answer. Ask only for decisions in step 2 and the freeze confirmation in step 6.

## Report to me

Report when each step completes, in 3 lines or fewer. At 1:00, send a status table:
task | state (done / in progress / blocked) | verify result. Then list the next three track A tasks
with the agent you will dispatch each one to.
