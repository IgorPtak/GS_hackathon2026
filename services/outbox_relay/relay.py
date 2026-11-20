"""Move committed outbox rows to Redis streams (transactional outbox, CLAUDE.md decision 4).

One batch = one Postgres transaction:
  1. lock unrelayed rows with `FOR UPDATE SKIP LOCKED` (replicas take disjoint batches);
  2. insert their `deliveries` rows (`ON CONFLICT DO NOTHING`, id = outbox id);
  3. XADD every job in one Redis pipeline;
  4. set `relayed_at`; commit.
If Redis fails at 3, the transaction rolls back and the rows are retried: nothing is lost. If the
process dies after 3 but before the commit, the next batch relays the rows again; the duplicate
job carries the same `delivery_id` and is absorbed by `delivery-done:<id>` in the delivery worker.

Because XADD happens before the commit, a delivery worker can read a job whose `deliveries` row is
not visible yet. The delivery worker (A-13) therefore upserts the row from the DeliveryJob instead
of assuming it exists. A row whose payload breaks its contract is copied to the matching
`<stream>-dlq` and marked relayed, so it is visible to ops but never blocks the rows behind it.
"""

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import asyncpg
import orjson
from alerting_contracts.alerts import DeliveryJob, OutboxKind, RunbookJob
from alerting_core.logging import get_logger
from alerting_core.metrics import LATENCY_BUCKETS
from prometheus_client import Counter, Gauge, Histogram
from pydantic import ValidationError
from redis.asyncio import Redis

log = get_logger(__name__)

DELIVERIES_STREAM = "deliveries"
RUNBOOK_JOBS_STREAM = "runbook-jobs"
_STREAM_MAXLEN = {DELIVERIES_STREAM: 1_000_000, RUNBOOK_JOBS_STREAM: 100_000}
_DEAD_LETTER_MAXLEN = 100_000
# Bounds one batch: a black-holed Redis must not hold row locks and a connection forever.
BATCH_TIMEOUT_SECONDS = 10.0

RELAYED = Counter("outbox_relayed_total", "Outbox rows relayed to a stream.", ["kind"])
INVALID = Counter("outbox_invalid_total", "Outbox rows skipped because their payload is invalid.")
BATCH_SECONDS = Histogram(
    "outbox_relay_batch_seconds", "Duration of one relay transaction.", buckets=LATENCY_BUCKETS
)
LAG_SECONDS = Gauge("outbox_relay_lag_seconds", "Age of the oldest row in the last relayed batch.")

_SELECT_BATCH = """
    SELECT id, kind, alert_id, payload, created_at
    FROM outbox
    WHERE relayed_at IS NULL
    ORDER BY id
    LIMIT $1
    FOR UPDATE SKIP LOCKED
"""
_INSERT_DELIVERIES = """
    INSERT INTO deliveries (
        id, alert_id, team, recipient_id, channel_id, channel_type, purpose, is_fallback
    )
    SELECT * FROM unnest(
        $1::bigint[], $2::uuid[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[],
        $8::bool[]
    )
    ON CONFLICT (id) DO NOTHING
"""
_MARK_RELAYED = "UPDATE outbox SET relayed_at = now() WHERE id = ANY($1::bigint[])"


def _dead_letter_stream(kind: str) -> str:
    stream = RUNBOOK_JOBS_STREAM if kind == OutboxKind.runbook_job else DELIVERIES_STREAM
    return f"{stream}-dlq"


class _Job:
    """One validated outbox row ready to be relayed."""

    __slots__ = ("outbox_id", "stream", "body", "delivery")

    def __init__(
        self, outbox_id: int, stream: str, body: bytes, delivery: DeliveryJob | None
    ) -> None:
        self.outbox_id = outbox_id
        self.stream = stream
        self.body = body
        self.delivery = delivery


def _parse_row(row: asyncpg.Record) -> _Job:
    """Validate the payload against its contract; raises ValidationError or ValueError."""
    payload: dict[str, Any] = row["payload"]
    if row["kind"] == OutboxKind.delivery:
        # The producer cannot know the outbox id inside its INSERT; the relay stamps it so the
        # id is the delivery's idempotency key end to end.
        job = DeliveryJob.model_validate({**payload, "delivery_id": row["id"]})
        return _Job(row["id"], DELIVERIES_STREAM, orjson.dumps(job.model_dump(mode="json")), job)
    if row["kind"] == OutboxKind.runbook_job:
        runbook_job = RunbookJob.model_validate(payload)
        body = orjson.dumps(runbook_job.model_dump(mode="json"))
        return _Job(row["id"], RUNBOOK_JOBS_STREAM, body, None)
    raise ValueError(f"unknown outbox kind {row['kind']!r}")


def _delivery_columns(jobs: list[_Job]) -> list[list[Any]]:
    deliveries = [job.delivery for job in jobs if job.delivery is not None]
    return [
        [d.delivery_id for d in deliveries],
        [d.alert_id for d in deliveries],
        [d.team for d in deliveries],
        [d.recipient_id for d in deliveries],
        [d.channel_id for d in deliveries],
        [str(d.channel_type) for d in deliveries],
        [str(d.purpose) for d in deliveries],
        [d.is_fallback for d in deliveries],
    ]


async def relay_batch(pool: asyncpg.Pool, redis: Redis, batch_size: int = 500) -> int:
    """Relay up to `batch_size` rows in one transaction; returns how many rows were handled."""
    started = time.perf_counter()
    async with pool.acquire() as connection, connection.transaction():
        rows = await connection.fetch(_SELECT_BATCH, batch_size)
        if not rows:
            LAG_SECONDS.set(0)
            return 0
        jobs: list[_Job] = []
        invalid: list[tuple[asyncpg.Record, str]] = []
        for row in rows:
            try:
                jobs.append(_parse_row(row))
            except (ValidationError, ValueError) as error:
                invalid.append((row, str(error)))

        if any(job.delivery is not None for job in jobs):
            await connection.execute(_INSERT_DELIVERIES, *_delivery_columns(jobs))
        async with redis.pipeline(transaction=False) as pipeline:
            for job in jobs:
                pipeline.xadd(
                    job.stream,
                    {"job": job.body},
                    maxlen=_STREAM_MAXLEN[job.stream],
                    approximate=True,
                )
            for row, error in invalid:
                pipeline.xadd(
                    _dead_letter_stream(row["kind"]),
                    {"job": orjson.dumps(row["payload"]), "error": error, "attempts": "0"},
                    maxlen=_DEAD_LETTER_MAXLEN,
                    approximate=True,
                )
            # Raises on any failed XADD, which rolls the whole transaction back.
            await pipeline.execute()
        await connection.execute(_MARK_RELAYED, [row["id"] for row in rows])

    for row, error in invalid:
        INVALID.inc()
        log.error(
            "outbox_entry_dead_lettered",
            extra={"outbox_id": row["id"], "alert_id": str(row["alert_id"]), "error": error},
        )
    for job in jobs:
        RELAYED.labels("delivery" if job.delivery is not None else "runbook_job").inc()
    LAG_SECONDS.set((datetime.now(UTC) - rows[0]["created_at"]).total_seconds())
    BATCH_SECONDS.observe(time.perf_counter() - started)
    return len(rows)


async def run_relay(
    pool: asyncpg.Pool,
    redis: Redis,
    stop: asyncio.Event,
    *,
    interval_seconds: float = 0.5,
    batch_size: int = 500,
    max_backoff_seconds: float = 5.0,
) -> None:
    """Relay until `stop` is set: again immediately after a full batch, else every interval."""
    backoff = interval_seconds
    log.info("outbox_relay_started", extra={"batch_size": batch_size})
    while not stop.is_set():
        try:
            # Cancelling the batch rolls its transaction back, so the timeout loses nothing.
            relayed = await asyncio.wait_for(
                relay_batch(pool, redis, batch_size), timeout=BATCH_TIMEOUT_SECONDS
            )
            backoff = interval_seconds
            if relayed >= batch_size:
                continue
            delay = interval_seconds
        except asyncio.CancelledError:
            raise
        except Exception:
            # Postgres or Redis down: the transaction rolled back, rows stay unrelayed.
            log.exception("outbox_relay_failed", extra={"retry_in_seconds": backoff})
            delay = backoff
            backoff = min(backoff * 2, max_backoff_seconds)
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
        except TimeoutError:
            pass
    log.info("outbox_relay_stopped")
