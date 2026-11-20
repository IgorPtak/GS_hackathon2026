"""Delivery attempts: idempotency, retries, dead letters, fallback and the circuit breaker."""

import time

from alerting_contracts.alerts import DeliveryJob

from plugins.channels.base import ChannelRejectedError, ChannelUnavailableError
from services.delivery.circuit import FAILURE_THRESHOLD, circuit_key
from services.delivery.retries import MOVE_DUE_SCRIPT, RETRIES_KEY, move_due_retries
from services.delivery.worker import done_key

from .conftest import email_job, stream_message


async def status_of(pool, delivery_id: int) -> str | None:  # noqa: ANN001
    return await pool.fetchval("SELECT status FROM deliveries WHERE id = $1", delivery_id)


async def verbs(pool) -> list[str]:  # noqa: ANN001
    return [r["verb"] for r in await pool.fetch("SELECT verb FROM audit_entries ORDER BY id")]


async def test_success_is_recorded_once_even_without_relay_row(pool, redis, plugin, worker) -> None:
    job = email_job()

    assert await worker.handle_batch([stream_message(job)]) == {}
    assert await worker.handle_batch([stream_message(job)]) == {}  # duplicate from the relay

    assert len(plugin.sent) == 1
    assert await status_of(pool, job.delivery_id) == "delivered"
    assert await redis.get(done_key(job.delivery_id)) == b"done"
    assert await verbs(pool) == ["delivery_delivered"]


async def test_in_flight_elsewhere_stays_pending(pool, redis, plugin, worker) -> None:
    job = email_job()
    await redis.set(done_key(job.delivery_id), "pending", ex=60)

    failures = await worker.handle_batch([stream_message(job)])

    assert list(failures) == ["1-0"]
    assert plugin.sent == []


async def test_unavailable_schedules_backoff_retry(pool, redis, plugin, worker) -> None:
    plugin.failures = [ChannelUnavailableError("503")]
    job = email_job()

    assert await worker.handle_batch([stream_message(job)]) == {}

    assert await status_of(pool, job.delivery_id) == "failed"
    assert await redis.exists(done_key(job.delivery_id)) == 0
    [(member, due_ms)] = await redis.zrange(RETRIES_KEY, 0, -1, withscores=True)
    retry = DeliveryJob.model_validate_json(member)
    assert retry.attempt == 1 and retry.not_before is not None
    assert due_ms > time.time() * 1000


async def test_retry_poller_moves_only_due_jobs(redis) -> None:
    script = redis.register_script(MOVE_DUE_SCRIPT)
    now_ms = int(time.time() * 1000)
    await redis.zadd(RETRIES_KEY, {"due": now_ms - 1, "later": now_ms + 60_000})

    assert await move_due_retries(redis, script) == 1

    [(_, fields)] = await redis.xrange("deliveries")
    assert fields[b"job"] == b"due"
    assert await redis.zrange(RETRIES_KEY, 0, -1) == [b"later"]


async def test_last_attempt_dead_letters_and_falls_back_to_ui(pool, redis, plugin, worker) -> None:
    plugin.failures = [ChannelUnavailableError("503")]
    job = email_job(attempt=4)  # email allows 5 attempts

    await worker.handle_batch([stream_message(job)])

    assert await status_of(pool, job.delivery_id) == "dead_lettered"
    [(_, fields)] = await redis.xrange("deliveries-dlq")
    assert fields[b"attempts"] == b"5"
    [outbox] = await pool.fetch("SELECT payload FROM outbox")
    fallback = DeliveryJob.model_validate(outbox["payload"])
    assert (fallback.channel_id, fallback.recipient_id, fallback.is_fallback) == ("ui", None, True)
    assert await verbs(pool) == ["delivery_dead_lettered", "delivery_fallback"]


async def test_rejected_dead_letters_at_once_and_fallback_never_chains(
    pool, redis, plugin, worker
) -> None:
    plugin.failures = [ChannelRejectedError("bad address"), ChannelRejectedError("again")]
    await worker.handle_batch([stream_message(email_job(delivery_id=1))])
    await worker.handle_batch([stream_message(email_job(delivery_id=2, is_fallback=True))])

    assert await status_of(pool, 1) == "dead_lettered"
    assert await status_of(pool, 2) == "dead_lettered"
    assert await pool.fetchval("SELECT count(*) FROM outbox") == 1  # only the first falls back


async def test_unknown_channel_is_dead_lettered(pool, redis, plugin, worker) -> None:
    job = email_job(channel_id="does-not-exist")

    await worker.handle_batch([stream_message(job)])

    assert await status_of(pool, job.delivery_id) == "dead_lettered"
    assert plugin.sent == []


async def test_invalid_job_goes_to_dead_letter_stream(pool, redis, plugin, worker) -> None:
    assert await worker.handle_batch([stream_message(b"{broken")]) == {}

    [(_, fields)] = await redis.xrange("deliveries-dlq")
    assert fields[b"job"] == b"{broken"


async def test_circuit_opens_then_half_opens(pool, redis, plugin, worker) -> None:
    plugin.failures = [ChannelUnavailableError("down")] * FAILURE_THRESHOLD
    for delivery_id in range(1, FAILURE_THRESHOLD + 1):
        await worker.handle_batch([stream_message(email_job(delivery_id=delivery_id))])
    assert await redis.hget(circuit_key("email"), "state") == b"open"

    job = email_job(delivery_id=100)
    await worker.handle_batch([stream_message(job)])  # open: rescheduled, no attempt spent
    assert plugin.sent == []
    assert await status_of(pool, 100) is None
    members = [DeliveryJob.model_validate_json(m) for m in await redis.zrange(RETRIES_KEY, 0, -1)]
    assert any(m.delivery_id == 100 and m.attempt == 0 for m in members)

    await redis.hset(circuit_key("email"), "opened_at", int(time.time() * 1000) - 11_000)
    await worker.handle_batch([stream_message(job)])  # half-open probe succeeds
    assert [sent.delivery_id for sent in plugin.sent] == [100]
    assert await redis.hget(circuit_key("email"), "state") == b"closed"


async def test_delivered_row_is_never_downgraded(pool, redis, plugin, worker) -> None:
    job = email_job()
    await worker.handle_batch([stream_message(job)])
    await redis.delete(done_key(job.delivery_id))  # key expired after 7 days
    plugin.failures = [ChannelRejectedError("late failure")]

    await worker.handle_batch([stream_message(job)])

    assert await status_of(pool, job.delivery_id) == "delivered"
