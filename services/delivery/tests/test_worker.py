"""Delivery attempts: idempotency, retries, dead letters, fallback and the circuit breaker."""

import time

from alerting_contracts.alerts import DeliveryJob
from prometheus_client import REGISTRY

from plugins.channels.base import ChannelRejectedError, ChannelUnavailableError
from services.delivery.circuit import FAILURE_THRESHOLD, CircuitBreaker, circuit_key
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
    plugin.failures = [RuntimeError("plugin bug")]  # not an outage: attempts count
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


async def test_redelivered_dead_letter_queues_one_fallback(pool, redis, plugin, worker) -> None:
    plugin.failures = [ChannelRejectedError("bad"), ChannelRejectedError("bad again")]
    job = email_job()

    await worker.handle_batch([stream_message(job)])
    await worker.handle_batch([stream_message(job)])  # crash before ack: same entry again

    assert await pool.fetchval("SELECT count(*) FROM outbox") == 1
    assert await verbs(pool) == ["delivery_dead_lettered", "delivery_fallback"]


async def test_sent_but_unrecorded_delivery_is_recorded_on_redelivery(
    pool, redis, plugin, worker
) -> None:
    job = email_job()
    await redis.set(done_key(job.delivery_id), "done")  # sender died after SET done

    await worker.handle_batch([stream_message(job)])

    assert plugin.sent == []
    assert await status_of(pool, job.delivery_id) == "delivered"
    assert await verbs(pool) == ["delivery_delivered"]


async def test_circuit_open_too_long_dead_letters_to_fallback(pool, redis, plugin, worker) -> None:
    job = email_job()
    await pool.execute(
        "INSERT INTO deliveries (id, alert_id, team, recipient_id, channel_id, channel_type,"
        " purpose, created_at) VALUES ($1, $2::uuid, 'rates', 'anna', 'email', 'email', 'alert',"
        " now() - interval '11 minutes')",
        job.delivery_id,
        job.alert_id,
    )
    await redis.hset(
        circuit_key("email"), mapping={"state": "open", "opened_at": int(time.time() * 1000)}
    )

    await worker.handle_batch([stream_message(job)])

    assert await status_of(pool, job.delivery_id) == "dead_lettered"
    assert await pool.fetchval("SELECT count(*) FROM outbox") == 1
    assert plugin.sent == []


async def test_open_circuit_parks_once_without_claiming(pool, redis, plugin, worker) -> None:
    job = email_job()
    await redis.hset(
        circuit_key("email"), mapping={"state": "open", "opened_at": int(time.time() * 1000)}
    )

    await worker.handle_batch([stream_message(job)])
    await worker.handle_batch([stream_message(job)])  # a redelivery parks the same job again

    assert await redis.exists(done_key(job.delivery_id)) == 0  # not claimed: no 60 s block
    assert await redis.zcard(RETRIES_KEY) == 1  # identical parked jobs collapse
    assert plugin.sent == []


async def test_success_does_not_close_an_open_circuit(redis) -> None:
    breaker = CircuitBreaker(redis)
    await redis.hset(circuit_key("email"), mapping={"state": "open", "opened_at": 1})

    await breaker.record_success("email")

    assert await redis.hget(circuit_key("email"), "state") == b"open"


async def insert_delivery_row(pool, job, age: str) -> None:  # noqa: ANN001
    await pool.execute(
        "INSERT INTO deliveries (id, alert_id, team, recipient_id, channel_id, channel_type,"
        f" purpose, created_at) VALUES ($1, $2::uuid, 'rates', 'anna', 'email', 'email', 'alert',"
        f" now() - interval '{age}')",
        job.delivery_id,
        job.alert_id,
    )


async def test_outage_does_not_use_up_attempts_within_the_budget(
    pool, redis, plugin, worker
) -> None:
    plugin.failures = [ChannelUnavailableError("smtp unavailable: Name or service not known")]
    job = email_job(attempt=4)  # would be the last of 5 attempts
    await insert_delivery_row(pool, job, "1 minute")

    await worker.handle_batch([stream_message(job)])

    assert await status_of(pool, job.delivery_id) == "failed"
    assert await redis.zcard(RETRIES_KEY) == 1
    assert await pool.fetchval("SELECT count(*) FROM outbox") == 0  # no fallback yet


async def test_outage_longer_than_the_budget_dead_letters_to_fallback(
    pool, redis, plugin, worker
) -> None:
    plugin.failures = [ChannelUnavailableError("503")]
    job = email_job(attempt=4)
    await insert_delivery_row(pool, job, "11 minutes")

    await worker.handle_batch([stream_message(job)])

    assert await status_of(pool, job.delivery_id) == "dead_lettered"
    assert await pool.fetchval("SELECT count(*) FROM outbox") == 1


async def test_delivery_post_relay_seconds_observes_primary_and_ignores_synthetic(
    pool, redis, plugin, worker
) -> None:
    def metric_count_sum() -> tuple[float, float]:
        labels = {"channel_type": "email"}
        count = REGISTRY.get_sample_value("delivery_post_relay_seconds_count", labels)
        total = REGISTRY.get_sample_value("delivery_post_relay_seconds_sum", labels)
        return float(count or 0.0), float(total or 0.0)

    c0, s0 = metric_count_sum()
    await worker.handle_batch([stream_message(email_job(delivery_id=1), entry_id="1-0")])
    assert metric_count_sum() == (c0, s0)

    real_id = f"{int((time.time() - 0.05) * 1000)}-0"
    await worker.handle_batch([stream_message(email_job(delivery_id=2), entry_id=real_id)])
    c1, s1 = metric_count_sum()
    assert c1 == c0 + 1 and s1 > s0

    await worker.handle_batch([stream_message(email_job(delivery_id=2), entry_id=real_id)])
    assert metric_count_sum() == (c1, s1)  # duplicate done ignores latency

    retried = email_job(delivery_id=3, attempt=1)
    await worker.handle_batch([stream_message(retried, entry_id=real_id)])
    assert metric_count_sum() == (c1, s1)  # retried jobs re-enter the stream and are excluded

    fallback = email_job(delivery_id=4, is_fallback=True)
    await worker.handle_batch([stream_message(fallback, entry_id=real_id)])
    assert metric_count_sum() == (c1, s1)  # fallback deliveries are excluded
