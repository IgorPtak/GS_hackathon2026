# services/runbook_runner

Consumes `runbook-jobs` (group `runbook-runners`); runs automatic runbook steps through the action
plugins, stops at approval steps (ActionRun + ApprovalRequest + `approval_request` deliveries via the
outbox) and resumes approved runs. /healthz and /metrics on 9104.

- `main.py` app, lifespan, consumer. `runner.py` job handler and `RunbookWalker` (step walk).
- `store.py` SQL for action_runs / approval_requests / audit checks. `approvals.py` delivery planning.
- Every job is one transaction that first takes `pg_advisory_xact_lock(hashtext(alert_id))`; SSE
  events are published after commit. Replays are idempotent (succeeded/failed/skipped steps are
  reused, a second approval is never created).
- Only automatic steps and approval-gated steps are walked; other manual steps are run from the UI.
- Metrics: `runbook_runner_jobs_total{job_type,outcome}`, `runbook_runner_action_runs_total{status}`.

Semantics to know:
- Plugin side effects are at-least-once: a crash after a plugin call (before the commit) rolls the
  job back and the entry is retried, so the action runs again.
- `running` is never visible outside the transaction; the UI sees only the final status of a job.
- A rejection stops the walk for that alert permanently (later steps never run).
- A job whose runbook is not loaded fails (stays pending, retried, then `runbook-jobs-dlq`);
  unparsable entries go straight to `runbook-jobs-dlq`.
- Plugin calls are bounded by the action timeout + 5 s; the lock wait by `lock_timeout` 120 s.

Owner: track B. Tasks: B-11. See `docs/IMPLEMENTATION_PLAN.md`.
