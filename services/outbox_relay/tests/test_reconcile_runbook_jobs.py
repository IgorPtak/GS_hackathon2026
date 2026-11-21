"""Reconciling relayed `runbook_job` rows whose stream entry was lost (A-40)."""

import asyncio
import uuid
from typing import Any

import asyncpg
from redis.asyncio import Redis

from services.outbox_relay.reconcile import RunbookJobReconciler, republish_stale_deliveries
from services.outbox_relay.relay import RUNBOOK_JOBS_STREAM, relay_batch

from .test_relay import insert_outbox, stream_jobs

RUNBOOK_ID = "workflow-failed"


async def insert_alert(pool: asyncpg.Pool) -> str:
    alert_id = str(uuid.uuid4())
    await pool.execute(
        "INSERT INTO alerts (id, rule_id, team, schema_profile_id, source_id, fingerprint,"
        " severity, title, first_seen, last_seen, runbook_id, last_event)"
        " VALUES ($1, 'r', 'rates', 'p', 's', 'f', 'error', 't', now(), now(), $2, '{}')",
        uuid.UUID(alert_id),
        RUNBOOK_ID,
    )
    return alert_id


async def insert_action_run(pool: asyncpg.Pool, alert_id: str, status: str) -> str:
    run_id = str(uuid.uuid4())
    await pool.execute(
        "INSERT INTO action_runs (id, alert_id, runbook_id, step_index, action_id, status,"
        " requested_by) VALUES ($1, $2, $3, 0, 'restart', $4, '{}')",
        uuid.UUID(run_id),
        uuid.UUID(alert_id),
        RUNBOOK_ID,
        status,
    )
    return run_id


def start_job(alert_id: str) -> dict[str, Any]:
    return {"job_type": "start_runbook", "alert_id": alert_id, "runbook_id": RUNBOOK_ID}


def execute_job(alert_id: str, run_id: str) -> dict[str, Any]:
    return {
        "job_type": "execute_action_run",
        "alert_id": alert_id,
        "runbook_id": RUNBOOK_ID,
        "action_run_id": run_id,
    }


async def relay_and_lose(pool: asyncpg.Pool, redis: Redis, age: str = "10 minutes") -> None:
    """Relay everything, then drop the stream as a Redis crash would, and age the rows."""
    await relay_batch(pool, redis)
    await redis.delete(RUNBOOK_JOBS_STREAM)
    await pool.execute(f"UPDATE outbox SET relayed_at = now() - interval '{age}'")


async def test_lost_start_runbook_job_is_republished_once(pool: asyncpg.Pool, redis: Redis) -> None:
    alert_id = await insert_alert(pool)
    await insert_outbox(pool, "runbook_job", start_job(alert_id))
    await relay_and_lose(pool, redis)
    reconciler = RunbookJobReconciler()

    assert await reconciler.republish_stale(pool, redis) == 1
    assert await reconciler.republish_stale(pool, redis) == 0  # guard: one copy per window

    assert await stream_jobs(redis, RUNBOOK_JOBS_STREAM) == [
        {**start_job(alert_id), "action_run_id": None}
    ]


async def test_started_runbook_is_left_alone(pool: asyncpg.Pool, redis: Redis) -> None:
    with_run = await insert_alert(pool)
    await insert_action_run(pool, with_run, "succeeded")
    with_audit = await insert_alert(pool)  # only manual steps: an audit entry but no runs
    await pool.execute(
        "INSERT INTO audit_entries (alert_id, actor, verb, detail)"
        " VALUES ($1, '{}', 'runbook_started', $2)",
        uuid.UUID(with_audit),
        {"runbook_id": RUNBOOK_ID},
    )
    missing_alert = str(uuid.uuid4())  # the runner skips jobs for deleted alerts
    for alert_id in (with_run, with_audit, missing_alert):
        await insert_outbox(pool, "runbook_job", start_job(alert_id))
    await relay_and_lose(pool, redis)

    assert await RunbookJobReconciler().republish_stale(pool, redis) == 0


async def test_approved_run_is_republished_and_started_run_is_not(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    alert_id = await insert_alert(pool)
    approved = await insert_action_run(pool, alert_id, "approved")
    running = await insert_action_run(pool, alert_id, "running")
    await insert_outbox(pool, "runbook_job", execute_job(alert_id, approved))
    await insert_outbox(pool, "runbook_job", execute_job(alert_id, running))
    await relay_and_lose(pool, redis)

    assert await RunbookJobReconciler().republish_stale(pool, redis) == 1

    [job] = await stream_jobs(redis, RUNBOOK_JOBS_STREAM)
    assert job["action_run_id"] == approved


async def test_recent_job_is_not_republished(pool: asyncpg.Pool, redis: Redis) -> None:
    alert_id = await insert_alert(pool)
    await insert_outbox(pool, "runbook_job", start_job(alert_id))
    await relay_and_lose(pool, redis, age="10 seconds")  # the runner may still be walking

    assert await RunbookJobReconciler().republish_stale(pool, redis) == 0


async def test_queued_runbook_jobs_get_no_copies(pool: asyncpg.Pool, redis: Redis) -> None:
    alert_id = await insert_alert(pool)
    await insert_outbox(pool, "runbook_job", start_job(alert_id))
    await relay_batch(pool, redis)
    await redis.xgroup_create(RUNBOOK_JOBS_STREAM, "runbook-runners", id="0")  # 1 unread
    await pool.execute("UPDATE outbox SET relayed_at = now() - interval '10 minutes'")

    assert await RunbookJobReconciler().republish_stale(pool, redis) == 0


async def test_replicas_publish_one_copy_per_round(pool: asyncpg.Pool, redis: Redis) -> None:
    alert_id = await insert_alert(pool)
    await insert_outbox(pool, "runbook_job", start_job(alert_id))
    await relay_and_lose(pool, redis)

    counts = await asyncio.gather(
        *(RunbookJobReconciler().republish_stale(pool, redis) for _ in range(4))
    )

    assert sum(counts) == 1
    assert len(await stream_jobs(redis, RUNBOOK_JOBS_STREAM)) == 1


async def test_floor_skips_settled_rows_and_stops_at_unsettled(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    started = await insert_alert(pool)
    await insert_action_run(pool, started, "succeeded")
    settled_id = await insert_outbox(pool, "runbook_job", start_job(started))
    stuck = await insert_alert(pool)
    await insert_outbox(pool, "runbook_job", start_job(stuck))
    await relay_and_lose(pool, redis)
    reconciler = RunbookJobReconciler()

    assert await reconciler.republish_stale(pool, redis) == 1
    assert reconciler.floor == settled_id  # the stuck job may need another copy later

    await pool.execute("UPDATE outbox SET relayed_at = now() - interval '2 hours'")
    assert await reconciler.republish_stale(pool, redis) == 0
    assert reconciler.floor > settled_id  # given up: logged once and no longer rescanned


async def test_runbook_jobs_do_not_touch_delivery_reconciliation(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    alert_id = await insert_alert(pool)
    await insert_outbox(pool, "runbook_job", start_job(alert_id))
    await relay_and_lose(pool, redis)

    assert await republish_stale_deliveries(pool, redis) == 0
    assert await redis.xlen("deliveries") == 0
    assert await stream_jobs(redis, RUNBOOK_JOBS_STREAM) == []
