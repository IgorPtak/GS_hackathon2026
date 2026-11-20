"""Runbook runner metrics; the shared stream counters come from alerting_core.metrics."""

from prometheus_client import Counter

RUNBOOK_JOBS = Counter(
    "runbook_runner_jobs_total",
    "Runbook jobs by outcome (handled, failed, invalid, skipped).",
    ["job_type", "outcome"],
)
ACTION_RUNS = Counter(
    "runbook_runner_action_runs_total",
    "Action run state changes, by resulting status.",
    ["status"],
)
