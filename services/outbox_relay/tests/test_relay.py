"""Outbox relay against the real Postgres and Redis (`docker compose up -d postgres redis`)."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import orjson
import pytest
from alerting_core.connections import create_database_pool
from alerting_core.settings import Settings
from redis.asyncio import Redis

from services.outbox_relay import reconcile
from services.outbox_relay.reconcile import republish_stale_deliveries
from services.outbox_relay.relay import (
    DELIVERIES_STREAM,
    RUNBOOK_JOBS_STREAM,
    relay_batch,
    run_relay,
)

REDIS_URL = "redis://localhost:6379/11"


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(REDIS_URL)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis on localhost:6379 is not running")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


MIGRATION = Path(__file__).parents[3] / "deploy/postgres/migrations/0001_initial.sql"
TEST_DATABASE = "alerting_relay_test"


async def ensure_test_database(settings: Settings) -> str:
    """A private database built from the migration, so a running compose relay never steals rows."""
    admin = await asyncpg.connect(settings.database_url)
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DATABASE)
        if not exists:
            await admin.execute(f"CREATE DATABASE {TEST_DATABASE}")
    finally:
        await admin.close()
    test_url = settings.database_url.rsplit("/", 1)[0] + f"/{TEST_DATABASE}"
    connection = await asyncpg.connect(test_url)
    try:
        await connection.execute(MIGRATION.read_text())  # idempotent
    finally:
        await connection.close()
    return test_url


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    try:
        test_url = await ensure_test_database(Settings())
    except OSError:
        pytest.skip("Postgres on localhost:5432 is not running")
    database_pool = await create_database_pool(Settings(database_url=test_url))
    await database_pool.execute("TRUNCATE outbox, deliveries")
    yield database_pool
    await database_pool.close()


def delivery_payload(alert_id: str, channel_id: str = "email") -> dict[str, Any]:
    return {
        "delivery_id": 0,  # stamped by the relay
        "alert_id": alert_id,
        "team": "rates",
        "recipient_id": "anna",
        "channel_id": channel_id,
        "channel_type": channel_id,
        "purpose": "alert",
        "content": {
            "title": "Rejected EUR 25000000 — LIMIT_BREACH",
            "severity": "error",
            "alert_url": f"http://localhost:5173/alerts/{alert_id}",
        },
    }


async def insert_outbox(pool: asyncpg.Pool, kind: str, payload: dict[str, Any]) -> int:
    return await pool.fetchval(
        "INSERT INTO outbox (kind, alert_id, payload) VALUES ($1, $2, $3) RETURNING id",
        kind,
        uuid.UUID(payload["alert_id"]),
        payload,
    )


async def stream_jobs(redis: Redis, stream: str) -> list[dict[str, Any]]:
    return [orjson.loads(fields[b"job"]) for _, fields in await redis.xrange(stream)]


async def unrelayed_count(pool: asyncpg.Pool) -> int:
    return await pool.fetchval("SELECT count(*) FROM outbox WHERE relayed_at IS NULL")


async def test_delivery_row_is_relayed_with_outbox_id(pool: asyncpg.Pool, redis: Redis) -> None:
    alert_id = str(uuid.uuid4())
    outbox_id = await insert_outbox(pool, "delivery", delivery_payload(alert_id))

    assert await relay_batch(pool, redis) == 1

    [job] = await stream_jobs(redis, DELIVERIES_STREAM)
    assert job["delivery_id"] == outbox_id
    assert job["alert_id"] == alert_id
    delivery = await pool.fetchrow("SELECT * FROM deliveries WHERE id = $1", outbox_id)
    assert delivery["status"] == "pending"
    assert delivery["channel_type"] == "email"
    assert delivery["recipient_id"] == "anna"
    assert await unrelayed_count(pool) == 0


async def test_runbook_job_goes_to_its_stream(pool: asyncpg.Pool, redis: Redis) -> None:
    alert_id = str(uuid.uuid4())
    payload = {"job_type": "start_runbook", "alert_id": alert_id, "runbook_id": "workflow-failed"}
    await insert_outbox(pool, "runbook_job", payload)

    assert await relay_batch(pool, redis) == 1

    assert await stream_jobs(redis, RUNBOOK_JOBS_STREAM) == [{**payload, "action_run_id": None}]
    assert await pool.fetchval("SELECT count(*) FROM deliveries") == 0


async def test_redis_failure_rolls_back_and_loses_nothing(pool: asyncpg.Pool, redis: Redis) -> None:
    await insert_outbox(pool, "delivery", delivery_payload(str(uuid.uuid4())))
    unreachable = Redis.from_url("redis://localhost:6390/0", socket_connect_timeout=0.2)

    with pytest.raises(Exception):  # noqa: B017 - any Redis connection error
        await relay_batch(pool, unreachable)
    await unreachable.aclose()

    assert await unrelayed_count(pool) == 1
    assert await pool.fetchval("SELECT count(*) FROM deliveries") == 0
    assert await relay_batch(pool, redis) == 1
    assert len(await stream_jobs(redis, DELIVERIES_STREAM)) == 1


async def test_invalid_row_is_skipped_without_blocking_others(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    alert_id = str(uuid.uuid4())
    await insert_outbox(pool, "delivery", {"alert_id": alert_id, "nonsense": True})
    await insert_outbox(pool, "delivery", delivery_payload(alert_id))

    assert await relay_batch(pool, redis) == 2

    assert len(await stream_jobs(redis, DELIVERIES_STREAM)) == 1
    assert await unrelayed_count(pool) == 0
    [(_, fields)] = await redis.xrange(f"{DELIVERIES_STREAM}-dlq")
    assert orjson.loads(fields[b"job"]) == {"alert_id": alert_id, "nonsense": True}
    assert fields[b"error"]


async def test_mixed_batch_relays_each_kind_to_its_stream(pool: asyncpg.Pool, redis: Redis) -> None:
    alert_id = str(uuid.uuid4())
    await insert_outbox(pool, "delivery", delivery_payload(alert_id))
    runbook = {"job_type": "start_runbook", "alert_id": alert_id, "runbook_id": "workflow-failed"}
    await insert_outbox(pool, "runbook_job", runbook)
    await insert_outbox(pool, "delivery", delivery_payload(alert_id, channel_id="ui"))

    assert await relay_batch(pool, redis) == 3

    assert len(await stream_jobs(redis, DELIVERIES_STREAM)) == 2
    assert len(await stream_jobs(redis, RUNBOOK_JOBS_STREAM)) == 1
    assert await pool.fetchval("SELECT count(*) FROM deliveries") == 2


async def test_existing_delivery_row_from_a_crashed_relay_is_kept(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    alert_id = str(uuid.uuid4())
    outbox_id = await insert_outbox(pool, "delivery", delivery_payload(alert_id))
    await pool.execute(
        "INSERT INTO deliveries (id, alert_id, team, channel_id, channel_type, purpose, status)"
        " VALUES ($1, $2, 'rates', 'email', 'email', 'alert', 'delivered')",
        outbox_id,
        uuid.UUID(alert_id),
    )

    assert await relay_batch(pool, redis) == 1

    status = await pool.fetchval("SELECT status FROM deliveries WHERE id = $1", outbox_id)
    assert status == "delivered"


async def test_concurrent_relays_relay_each_row_exactly_once(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    alert_id = str(uuid.uuid4())
    rows = [("delivery", uuid.UUID(alert_id), delivery_payload(alert_id)) for _ in range(1000)]
    await pool.executemany("INSERT INTO outbox (kind, alert_id, payload) VALUES ($1, $2, $3)", rows)

    async def drain() -> None:
        while await relay_batch(pool, redis, batch_size=100):
            pass

    await asyncio.gather(*(drain() for _ in range(4)))

    jobs = await stream_jobs(redis, DELIVERIES_STREAM)
    assert len(jobs) == 1000
    assert len({job["delivery_id"] for job in jobs}) == 1000
    assert await unrelayed_count(pool) == 0


async def test_run_relay_picks_up_new_rows_until_stopped(pool: asyncpg.Pool, redis: Redis) -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(run_relay(pool, redis, stop, interval_seconds=0.05))
    await insert_outbox(pool, "delivery", delivery_payload(str(uuid.uuid4())))

    for _ in range(100):
        if await unrelayed_count(pool) == 0:
            break
        await asyncio.sleep(0.02)
    stop.set()
    await asyncio.wait_for(task, timeout=2)

    assert await unrelayed_count(pool) == 0
    assert len(await stream_jobs(redis, DELIVERIES_STREAM)) == 1


async def test_lost_relayed_job_is_republished_once(pool: asyncpg.Pool, redis: Redis) -> None:
    outbox_id = await insert_outbox(pool, "delivery", delivery_payload(str(uuid.uuid4())))
    await relay_batch(pool, redis)
    await redis.delete("deliveries")  # Redis lost the entry; Postgres still says pending
    await pool.execute("UPDATE deliveries SET created_at = now() - interval '1 minute'")

    assert await republish_stale_deliveries(pool, redis) == 1
    assert await republish_stale_deliveries(pool, redis) == 0  # guard: one copy per window

    [job] = await stream_jobs(redis, "deliveries")
    assert job["delivery_id"] == outbox_id


async def test_recent_or_finished_deliveries_are_left_alone(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    await insert_outbox(pool, "delivery", delivery_payload(str(uuid.uuid4())))
    finished = await insert_outbox(pool, "delivery", delivery_payload(str(uuid.uuid4())))
    await relay_batch(pool, redis)
    await redis.delete("deliveries")
    await pool.execute("UPDATE deliveries SET status = 'delivered' WHERE id = $1", finished)

    assert await republish_stale_deliveries(pool, redis) == 0  # first one is only seconds old
    await pool.execute("UPDATE deliveries SET created_at = now() - interval '1 minute'")
    assert await republish_stale_deliveries(pool, redis) == 1  # the delivered one stays done


async def test_backlogged_workers_get_no_copies(
    pool: asyncpg.Pool, redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reconcile, "MAX_LAG", 2)
    for _ in range(3):
        await insert_outbox(pool, "delivery", delivery_payload(str(uuid.uuid4())))
    await relay_batch(pool, redis)
    await redis.xgroup_create("deliveries", "delivery-workers", id="0")  # 3 unread: queued
    await pool.execute("UPDATE deliveries SET created_at = now() - interval '1 minute'")

    assert await republish_stale_deliveries(pool, redis) == 0


async def test_reconcile_pages_past_guarded_rows(
    pool: asyncpg.Pool, redis: Redis, monkeypatch
) -> None:
    monkeypatch.setattr(reconcile, "_BATCH", 2)
    ids = [
        await insert_outbox(pool, "delivery", delivery_payload(str(uuid.uuid4()))) for _ in range(5)
    ]
    await relay_batch(pool, redis)
    await redis.delete("deliveries")
    await pool.execute("UPDATE deliveries SET created_at = now() - interval '1 minute'")
    for delivery_id in ids[:2]:  # the first page is already guarded (e.g. parked jobs)
        await redis.set(reconcile.reconciled_key(delivery_id), 1)

    assert await republish_stale_deliveries(pool, redis) == 3


def test_parsed_delivery_body_round_trips_through_the_contract() -> None:
    from alerting_contracts.alerts import DeliveryJob

    from services.outbox_relay.relay import _parse_row

    payload = DeliveryJob(
        delivery_id=0,
        alert_id="a1",
        team="ops",
        recipient_id="r1",
        channel_id="c1",
        channel_type="ui",
        purpose="alert",
        content={
            "title": "t",
            "body": "b",
            "severity": "info",
            "fields": [],
            "alert_url": "http://x/a",
        },
    ).model_dump(mode="json")
    job = _parse_row({"id": 7, "kind": "delivery", "payload": payload})  # type: ignore[arg-type]
    assert DeliveryJob.model_validate_json(job.body) == job.delivery
    assert orjson.loads(job.body)["delivery_id"] == 7
