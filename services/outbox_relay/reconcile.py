"""Re-publish relayed delivery and runbook jobs that never reached their worker.

The relay marks an outbox row relayed once its XADD succeeded, so Postgres says "on the way" from
then on. If Redis then loses the stream entry (a crash inside the AOF fsync window, a restore,
a trim) the job is gone while its `deliveries` row stays `pending` forever. Postgres is the
source of truth, so this loop rebuilds such jobs from `outbox.payload` and XADDs them again.

Safe to repeat: the delivery worker is idempotent by delivery id (`delivery-done:<id>`), so a
job that was only slow is never sent twice. A job parked behind an open circuit also stays
`pending`, so each delivery is re-published at most once per RECONCILE_GUARD_SECONDS
(`delivery-reconciled:<id>` SET NX) to keep copies from piling up.

While `delivery-workers` is behind (lag > MAX_LAG) a queued job also looks "pending for 30 s",
so the loop skips that tick instead of adding copies to a backlog.

Runbook jobs have no `deliveries` row, so "never started" is read from the runner's own writes
(see `_SELECT_RUNBOOK_JOBS`). Known gap: a `failed` delivery whose `delivery-retries` entry was
lost is not reconciled.
"""

import asyncio
from contextlib import suppress
from datetime import UTC, datetime

import asyncpg
from alerting_core.logging import get_logger
from alerting_core.metrics import parse_group_lags
from prometheus_client import Counter
from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import ResponseError

from .relay import DELIVERIES_STREAM, RUNBOOK_JOBS_STREAM, _parse_row

log = get_logger(__name__)

# Normal deliveries leave `pending` in well under a second; 30 s means the job is lost.
STALE_AFTER_SECONDS = 30
RECONCILE_INTERVAL_SECONDS = 10.0
# Longer than the delivery worker's MAX_OUTAGE_SECONDS, so a parked job gets one extra copy.
RECONCILE_GUARD_SECONDS = 660
_BATCH = 500
# Above this many unread entries "pending for 30 s" may only mean "still queued".
MAX_LAG = 1000
_MAXLEN = 1_000_000  # same bound as the relay's XADD

# The runner keeps one transaction open for a whole walk (every automatic step, every attempt),
# so its progress is invisible until commit; 30 s would copy jobs that are merely slow.
RUNBOOK_STALE_AFTER_SECONDS = 300
# Runbook jobs are few: any unread entry may be the "missing" one, so wait until the group is idle.
RUNBOOK_MAX_LAG = 0
# A job still not started this long after relay (runbook deleted, job dead-lettered) has had
# several copies; it is logged once and no longer rescanned, so the scan stays short.
RUNBOOK_GIVE_UP_AFTER_SECONDS = 3600

REPUBLISHED = Counter(
    "outbox_reconciled_total", "Relayed delivery jobs re-published because they were lost."
)
RUNBOOK_JOBS_REPUBLISHED = Counter(
    "outbox_runbook_jobs_reconciled_total",
    "Relayed runbook jobs re-published because they were lost.",
)

# deliveries.created_at is set in the relay's transaction (same moment as relayed_at) and is
# covered by deliveries_unfinished_idx (status, created_at); keyset paging on (created_at, id).
_SELECT_STALE = """
    SELECT o.id, o.kind, o.alert_id, o.payload, o.created_at, d.created_at AS delivery_created_at
    FROM deliveries d JOIN outbox o ON o.id = d.id
    WHERE d.status = 'pending'
      AND d.created_at < now() - make_interval(secs => $1)
      AND (d.created_at, d.id) > ($2, $3)
    ORDER BY d.created_at, d.id
    LIMIT $4
"""


# "Work started" = anything the runner commits for the job. start_runbook: an action run of that
# runbook or its `runbook_started` audit (a runbook with only manual steps creates no run);
# a deleted alert counts as started because the runner skips it. execute_action_run: the run has
# left `approved` (the runner sets `running` first, the API never sets it back). Ids are compared
# as text so one bad payload cannot fail the cast for the whole batch.
_SELECT_RUNBOOK_JOBS = """
    SELECT o.id, o.kind, o.alert_id, o.payload, o.created_at, o.relayed_at,
        o.relayed_at < now() - make_interval(secs => $2) AS is_stale,
        o.relayed_at < now() - make_interval(secs => $3) AS is_abandoned,
        CASE o.payload->>'job_type'
            WHEN 'start_runbook' THEN
                EXISTS (SELECT 1 FROM action_runs r WHERE r.alert_id = o.alert_id
                        AND r.runbook_id = o.payload->>'runbook_id')
                OR EXISTS (SELECT 1 FROM audit_entries a WHERE a.alert_id = o.alert_id
                           AND a.verb = 'runbook_started'
                           AND a.detail->>'runbook_id' = o.payload->>'runbook_id')
                OR NOT EXISTS (SELECT 1 FROM alerts al WHERE al.id = o.alert_id)
            WHEN 'execute_action_run' THEN
                NOT EXISTS (SELECT 1 FROM action_runs r WHERE r.alert_id = o.alert_id
                            AND r.id::text = o.payload->>'action_run_id'
                            AND r.status = 'approved')
            ELSE true
        END AS is_started
    FROM outbox o
    WHERE o.kind = 'runbook_job' AND o.id > $1
    ORDER BY o.id
    LIMIT $4
"""


def reconciled_key(delivery_id: int) -> str:
    return f"delivery-reconciled:{delivery_id}"


def runbook_job_reconciled_key(outbox_id: int) -> str:
    return f"runbook-job-reconciled:{outbox_id}"


async def is_backlogged(
    redis: Redis, stream: str = DELIVERIES_STREAM, max_lag: int | None = None
) -> bool:
    """True while a stream's consumers are behind: queued jobs cannot be told from lost ones."""
    limit = MAX_LAG if max_lag is None else max_lag  # read at call time (tests patch MAX_LAG)
    try:
        groups = await redis.xinfo_groups(stream)
    except ResponseError:
        return False  # no stream (Redis emptied): nothing queued, so nothing to confuse
    return any(lag > limit for lag in parse_group_lags(groups).values())


async def republish_stale_deliveries(pool: asyncpg.Pool, redis: Redis) -> int:
    """XADD lost delivery jobs again; returns how many were re-published."""
    if await is_backlogged(redis):
        return 0
    republished = 0
    cursor: tuple[datetime, int] = (datetime.min.replace(tzinfo=UTC), 0)
    while rows := await pool.fetch(_SELECT_STALE, STALE_AFTER_SECONDS, *cursor, _BATCH):
        for row in rows:
            republished += await _republish(redis, row)
        last = rows[-1]
        cursor = (last["delivery_created_at"], last["id"])
        if len(rows) < _BATCH:
            break
    REPUBLISHED.inc(republished)
    return republished


async def _republish(redis: Redis, row: asyncpg.Record, key: str | None = None) -> int:
    key = key or reconciled_key(row["id"])
    if not await redis.set(key, 1, nx=True, ex=RECONCILE_GUARD_SECONDS):
        return 0  # already re-published recently (e.g. parked behind an open circuit)
    try:
        job = _parse_row(row)
    except (ValidationError, ValueError):
        return 0  # the relay already dead-lettered it
    try:
        await redis.xadd(job.stream, {"job": job.body}, maxlen=_MAXLEN, approximate=True)
    except Exception:
        await redis.delete(key)  # no copy went out: let the next tick try again
        raise
    if row["kind"] == "delivery":
        extra = {"delivery_id": row["id"], "alert_id": str(row["alert_id"])}
        log.warning("delivery_republished", extra=extra)
    else:
        extra = {"outbox_id": row["id"], "alert_id": str(row["alert_id"])}
        log.warning("runbook_job_republished", extra=extra)
    return 1


class RunbookJobReconciler:
    """Re-publishes `runbook_job` outbox rows that were relayed but never started.

    Outbox rows are never deleted and `outbox` has no index on kind or relayed_at, so the scan
    starts after `floor`: the highest id below which every runbook job is settled (started,
    invalid or given up). Each replica keeps its own floor; after a restart it scans once from 0.

    Duplicates are harmless (checked in services/runbook_runner/runner.py): every job takes the
    per-alert advisory lock; `start_runbook` writes `runbook_started` only if absent and the walk
    skips steps whose latest run is succeeded, failed at max attempts, skipped or held;
    `execute_action_run` re-reads the run FOR UPDATE and skips it unless it is still `approved`.
    The SET NX guard (as for deliveries) keeps relay replicas from adding one copy each.
    """

    def __init__(self) -> None:
        self.floor = 0

    async def republish_stale(self, pool: asyncpg.Pool, redis: Redis) -> int:
        """XADD lost runbook jobs again; returns how many were re-published."""
        if await is_backlogged(redis, RUNBOOK_JOBS_STREAM, RUNBOOK_MAX_LAG):
            return 0
        republished = 0
        cursor = self.floor
        is_settled_prefix = True
        while rows := await pool.fetch(
            _SELECT_RUNBOOK_JOBS,
            cursor,
            RUNBOOK_STALE_AFTER_SECONDS,
            RUNBOOK_GIVE_UP_AFTER_SECONDS,
            _BATCH,
        ):
            for row in rows:
                state = await self._reconcile_row(redis, row)
                republished += state == "republished"
                is_settled_prefix = is_settled_prefix and state in ("settled", "abandoned")
                if is_settled_prefix:
                    self.floor = row["id"]
                    if state == "abandoned":  # logged once: the floor never moves back
                        log.error(
                            "runbook_job_abandoned",
                            extra={"outbox_id": row["id"], "alert_id": str(row["alert_id"])},
                        )
            cursor = rows[-1]["id"]
            if len(rows) < _BATCH:
                break
        RUNBOOK_JOBS_REPUBLISHED.inc(republished)
        return republished

    async def _reconcile_row(self, redis: Redis, row: asyncpg.Record) -> str:
        """Returns settled, abandoned, waiting (may need a copy later) or republished."""
        if row["relayed_at"] is None:
            return "waiting"  # the relay has not taken it yet
        if row["is_started"]:
            return "settled"
        try:
            _parse_row(row)
        except (ValidationError, ValueError):
            return "settled"  # the relay already dead-lettered it
        if row["is_abandoned"]:
            return "abandoned"
        if not row["is_stale"]:
            return "waiting"
        key = runbook_job_reconciled_key(row["id"])
        return "republished" if await _republish(redis, row, key) else "waiting"


async def run_reconciler(
    pool: asyncpg.Pool,
    redis: Redis,
    stop: asyncio.Event,
    interval_seconds: float = RECONCILE_INTERVAL_SECONDS,
) -> None:
    """Reconcile every interval until stopped; errors are logged and retried next tick."""
    runbook_jobs = RunbookJobReconciler()
    while not stop.is_set():
        try:
            await republish_stale_deliveries(pool, redis)
        except asyncio.CancelledError:
            raise
        except Exception:  # Postgres or Redis down: try again next tick
            log.exception("delivery_reconcile_failed")
        try:
            await runbook_jobs.republish_stale(pool, redis)
        except asyncio.CancelledError:
            raise
        except Exception:  # Postgres or Redis down: try again next tick
            log.exception("runbook_job_reconcile_failed")
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
