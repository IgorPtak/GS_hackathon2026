"""Re-publish relayed delivery jobs that never reached a delivery worker.

The relay marks an outbox row relayed once its XADD succeeded, so Postgres says "on the way" from
then on. If Redis then loses the stream entry (a crash inside the AOF fsync window, a restore,
a trim) the job is gone while its `deliveries` row stays `pending` forever. Postgres is the
source of truth, so this loop rebuilds such jobs from `outbox.payload` and XADDs them again.

Safe to repeat: the delivery worker is idempotent by delivery id (`delivery-done:<id>`), so a
job that was only slow is never sent twice. A job parked behind an open circuit also stays
`pending`, so each delivery is re-published at most once per RECONCILE_GUARD_SECONDS
(`delivery-reconciled:<id>` SET NX) to keep copies from piling up.
"""

import asyncio
from contextlib import suppress

import asyncpg
from alerting_core.logging import get_logger
from prometheus_client import Counter
from pydantic import ValidationError
from redis.asyncio import Redis

from .relay import _parse_row

log = get_logger(__name__)

# Normal deliveries leave `pending` in well under a second; 30 s means the job is lost.
STALE_AFTER_SECONDS = 30
RECONCILE_INTERVAL_SECONDS = 10.0
# Longer than the delivery worker's MAX_OUTAGE_SECONDS, so a parked job gets one extra copy.
RECONCILE_GUARD_SECONDS = 660
_BATCH = 500

REPUBLISHED = Counter(
    "outbox_reconciled_total", "Relayed delivery jobs re-published because they were lost."
)

_SELECT_STALE = """
    SELECT o.id, o.kind, o.alert_id, o.payload, o.created_at
    FROM deliveries d JOIN outbox o ON o.id = d.id
    WHERE d.status = 'pending'
      AND o.relayed_at < now() - make_interval(secs => $1)
    ORDER BY o.id
    LIMIT $2
"""


def reconciled_key(delivery_id: int) -> str:
    return f"delivery-reconciled:{delivery_id}"


async def republish_stale_deliveries(pool: asyncpg.Pool, redis: Redis) -> int:
    """XADD lost delivery jobs again; returns how many were re-published."""
    rows = await pool.fetch(_SELECT_STALE, STALE_AFTER_SECONDS, _BATCH)
    republished = 0
    for row in rows:
        if not await redis.set(reconciled_key(row["id"]), 1, nx=True, ex=RECONCILE_GUARD_SECONDS):
            continue  # already re-published recently (e.g. parked behind an open circuit)
        try:
            job = _parse_row(row)
        except (ValidationError, ValueError):
            continue  # the relay already dead-lettered it
        await redis.xadd(job.stream, {"job": job.body})
        republished += 1
        log.warning(
            "delivery_republished",
            extra={"delivery_id": row["id"], "alert_id": str(row["alert_id"])},
        )
    REPUBLISHED.inc(republished)
    return republished


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
