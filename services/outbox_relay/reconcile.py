"""Re-publish relayed delivery jobs that never reached a delivery worker.

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

Known gaps: runbook-job outbox rows have no `deliveries` row and are not reconciled; a `failed`
delivery whose `delivery-retries` entry was lost is not reconciled either.
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

from .relay import DELIVERIES_STREAM, _parse_row

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

REPUBLISHED = Counter(
    "outbox_reconciled_total", "Relayed delivery jobs re-published because they were lost."
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


def reconciled_key(delivery_id: int) -> str:
    return f"delivery-reconciled:{delivery_id}"


async def is_backlogged(redis: Redis) -> bool:
    """True while delivery workers are behind, when queued jobs cannot be told from lost ones."""
    try:
        groups = await redis.xinfo_groups(DELIVERIES_STREAM)
    except ResponseError:
        return False  # no stream (Redis emptied): nothing queued, so nothing to confuse
    return any(lag > MAX_LAG for lag in parse_group_lags(groups).values())


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


async def _republish(redis: Redis, row: asyncpg.Record) -> int:
    key = reconciled_key(row["id"])
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
    log.warning(
        "delivery_republished", extra={"delivery_id": row["id"], "alert_id": str(row["alert_id"])}
    )
    return 1


async def run_reconciler(
    pool: asyncpg.Pool,
    redis: Redis,
    stop: asyncio.Event,
    interval_seconds: float = RECONCILE_INTERVAL_SECONDS,
) -> None:
    """Reconcile every interval until stopped; errors are logged and retried next tick."""
    while not stop.is_set():
        try:
            await republish_stale_deliveries(pool, redis)
        except asyncio.CancelledError:
            raise
        except Exception:  # Postgres or Redis down: try again next tick
            log.exception("delivery_reconcile_failed")
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
