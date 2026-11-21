"""scripts/replay_dead_letters.py: a dead-lettered job delivers after replay, exactly once."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from alerting_contracts.alerts import AuditVerb, DeliveryStatus

from plugins.channels.base import ChannelRejectedError, ChannelUnavailableError
from services.delivery.records import Outcome, record_outcome

from .conftest import email_job, load_snapshot, stream_message

# scripts/ is not a package; load the script the way `uv run python scripts/...` runs it.
_SPEC = importlib.util.spec_from_file_location(
    "replay_dead_letters", Path(__file__).parents[3] / "scripts/replay_dead_letters.py"
)
replay_module = importlib.util.module_from_spec(_SPEC)  # type: ignore[arg-type]
_SPEC.loader.exec_module(replay_module)  # type: ignore[union-attr]


async def test_replayed_dead_letter_is_delivered_without_a_second_fallback(
    pool, redis, plugin, worker
) -> None:
    plugin.failures = [ChannelRejectedError("mailbox full")]
    job = email_job()
    await worker.handle_batch([stream_message(job)])
    assert await redis.xlen("deliveries-dlq") == 1

    result = await replay_module.replay(redis, pool, {job.delivery_id}, is_dry_run=False)
    assert result.replayed == 1
    [(_, fields)] = await redis.xrange("deliveries")
    await worker.handle_batch([stream_message(job.model_validate_json(fields[b"job"]))])

    status = await pool.fetchval("SELECT status FROM deliveries WHERE id = $1", job.delivery_id)
    assert status == "delivered"
    assert await redis.xlen("deliveries-dlq") == 0
    assert await pool.fetchval("SELECT count(*) FROM outbox") == 1  # the original fallback only


async def test_dry_run_and_filter_leave_the_dlq_untouched(pool, redis, plugin, worker) -> None:
    plugin.failures = [ChannelRejectedError("x")]
    await worker.handle_batch([stream_message(email_job())])

    assert (await replay_module.replay(redis, pool, {999}, is_dry_run=False)).replayed == 0
    assert (await replay_module.replay(redis, pool, None, is_dry_run=True)).replayed == 1
    assert await redis.xlen("deliveries-dlq") == 1


async def test_replay_all_pages_through_deleted_entries(
    pool, redis, plugin, worker, monkeypatch
) -> None:
    monkeypatch.setattr(replay_module, "_PAGE", 2)
    plugin.failures = [ChannelRejectedError("x")] * 5
    for delivery_id in range(1, 6):
        await worker.handle_batch([stream_message(email_job(delivery_id))])

    result = await replay_module.replay(redis, pool, None, is_dry_run=False)

    assert result.replayed == 5
    assert await redis.xlen("deliveries-dlq") == 0
    assert await redis.xlen("deliveries") == 5


async def test_replay_that_fails_again_queues_no_second_fallback(
    pool, redis, plugin, worker
) -> None:
    job = email_job()
    plugin.failures = [ChannelRejectedError("x")]
    await worker.handle_batch([stream_message(job)])
    await pool.execute("UPDATE deliveries SET created_at = now() - interval '1 hour'")
    await replay_module.replay(redis, pool, None, is_dry_run=False)
    [(_, fields)] = await redis.xrange("deliveries")
    replayed = job.model_validate_json(fields[b"job"])

    plugin.failures = [ChannelUnavailableError("down")]  # still down: retried, fresh budget
    await worker.handle_batch([stream_message(replayed)])
    assert await redis.zcard("delivery-retries") == 1
    plugin.failures = [ChannelRejectedError("still broken")]  # then dead-lettered again
    await worker.handle_batch([stream_message(replayed.model_copy(update={"attempt": 1}))])

    assert await pool.fetchval("SELECT count(*) FROM outbox") == 1


async def test_worker_timeout_counts_as_an_outage(pool, redis, plugin, worker) -> None:
    plugin.failures = [TimeoutError()]
    job = email_job(attempt=4)

    await worker.handle_batch([stream_message(job)])

    assert await redis.zcard("delivery-retries") == 1  # retried, not dead-lettered


async def test_record_outcome_idempotency(pool) -> None:
    ui = load_snapshot().of_kind("channel")["ui"]
    job1 = email_job(delivery_id=10)
    failed = Outcome(DeliveryStatus.failed, AuditVerb.delivery_failed, 1, "503")
    delivered = Outcome(
        DeliveryStatus.delivered, AuditVerb.delivery_delivered, 2, None, datetime.now(UTC)
    )
    dead = Outcome(DeliveryStatus.dead_lettered, AuditVerb.delivery_dead_lettered, 1, "rejected")
    assert (await record_outcome(pool, job1, failed)).delivery is not None
    first_done = await record_outcome(pool, job1, delivered)
    assert first_done.delivery is not None and len(first_done.audit) == 1
    assert (await record_outcome(pool, job1, delivered)).delivery is None
    assert (await record_outcome(pool, job1, failed)).delivery is None
    assert (await record_outcome(pool, job1, dead, fallback=ui)).delivery is None
    assert await pool.fetchval("SELECT status FROM deliveries WHERE id = $1", 10) == "delivered"

    job2 = email_job(delivery_id=11)
    first_dead = await record_outcome(pool, job2, dead, fallback=ui)
    assert first_dead.delivery is not None and [a.verb for a in first_dead.audit] == [
        AuditVerb.delivery_dead_lettered,
        AuditVerb.delivery_fallback,
    ]
    assert (await record_outcome(pool, job2, dead, fallback=ui)).delivery is None
    assert (await record_outcome(pool, job2, failed)).delivery is not None
    assert await pool.fetchval("SELECT status FROM deliveries WHERE id = $1", 11) == "dead_lettered"
    assert (await record_outcome(pool, job2, dead, fallback=ui)).delivery is None
    assert await pool.fetchval("SELECT count(*) FROM outbox") == 1
