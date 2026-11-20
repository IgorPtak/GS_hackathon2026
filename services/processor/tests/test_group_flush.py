"""Group windows end to end: buffer in batches, flush once per window across replicas."""

import asyncio
import time

from alerting_core.settings import Settings

from services.processor.groups import DEADLINES_KEY, RETRY_AFTER_MS, GroupFlusher

from .conftest import FakeRegistry, fixture_payload, message

RULE_ID = "pricing-stale-feed"
INSTRUMENTS = ["EURUSD", "GBPUSD", "USDJPY", "XS1", "XS2"]


def stale(instrument: str, feed: str = "reuters") -> dict:
    payload = fixture_payload("pricing_price_stale.json")
    payload["instrument"] = instrument
    payload["feed"] = feed
    return payload


def flusher(pool, redis, snapshot) -> GroupFlusher:  # noqa: ANN001
    return GroupFlusher(pool, redis, FakeRegistry(snapshot), Settings())  # type: ignore[arg-type]


def later_ms(seconds: float) -> int:
    return int((time.time() + seconds) * 1000)


async def summaries(pool):  # noqa: ANN001, ANN201
    return await pool.fetch("SELECT * FROM alerts WHERE is_group_summary ORDER BY group_key")


async def test_two_processors_and_flushers_make_one_summary_per_key(
    pool, redis, make_processor, snapshot
) -> None:
    events = [
        message(stale(INSTRUMENTS[i % 5], f"feed-{i % 7}"), "pricing-log") for i in range(1000)
    ]
    processors = [make_processor(), make_processor()]

    await asyncio.gather(*(p.handle_batch(events[i::2]) for i, p in enumerate(processors)))
    assert await summaries(pool) == []  # the window is still open

    flushers = [flusher(pool, redis, snapshot) for _ in range(2)]
    await asyncio.gather(*(f.flush_due(later_ms(11)) for f in flushers))

    rows = await summaries(pool)
    assert [row["group_key"] for row in rows] == sorted(INSTRUMENTS)
    assert sum(row["count"] for row in rows) == 1000
    assert all(len(row["group_members"]) == 7 for row in rows)
    verbs = await pool.fetch("SELECT verb FROM audit_entries")
    assert {row["verb"] for row in verbs} == {"alert_grouped"}
    purposes = await pool.fetch(
        "SELECT payload->>'purpose' AS purpose FROM outbox WHERE kind = 'delivery'"
    )
    assert {row["purpose"] for row in purposes} == {"group_summary"}
    assert await redis.zcard(DEADLINES_KEY) == 0


async def test_window_is_not_flushed_before_its_deadline(
    pool, redis, make_processor, snapshot
) -> None:
    await make_processor().handle_batch([message(stale("EURUSD"), "pricing-log")])

    assert await flusher(pool, redis, snapshot).flush_due(later_ms(5)) == 0
    assert await flusher(pool, redis, snapshot).flush_due(later_ms(11)) == 1


async def test_claimed_window_of_a_dead_flusher_is_reflushed_once(
    pool, redis, make_processor, snapshot
) -> None:
    await make_processor().handle_batch([message(stale("EURUSD"), "pricing-log")])
    dead = flusher(pool, redis, snapshot)
    claimed = await dead._claim(
        keys=[DEADLINES_KEY], args=[later_ms(11), 100, RETRY_AFTER_MS, RETRY_AFTER_MS + 60_000]
    )
    assert len(claimed) == 1  # claimed, then the process died before writing the alert

    rescuer = flusher(pool, redis, snapshot)
    assert await rescuer.flush_due(later_ms(12)) == 0  # retry not due yet
    assert await rescuer.flush_due(later_ms(11 + RETRY_AFTER_MS / 1000 + 1)) == 1
    assert len(await summaries(pool)) == 1


async def test_reflush_of_a_committed_window_creates_no_duplicate(
    pool, redis, make_processor, snapshot
) -> None:
    await make_processor().handle_batch([message(stale("EURUSD"), "pricing-log")])
    worker = flusher(pool, redis, snapshot)
    [raw] = await worker._claim(
        keys=[DEADLINES_KEY], args=[later_ms(11), 100, RETRY_AFTER_MS, RETRY_AFTER_MS + 60_000]
    )
    flushing = raw.decode()
    events = await redis.lrange(flushing, 0, -1)

    assert await worker._flush_window(flushing) == 1
    await redis.rpush(flushing, *events)  # as if the finish step was lost
    assert await worker._flush_window(flushing) == 0

    assert len(await summaries(pool)) == 1
    assert await pool.fetchval("SELECT count(*) FROM audit_entries") == 1


async def test_events_after_the_flush_open_a_new_window(
    pool, redis, make_processor, snapshot
) -> None:
    processor = make_processor()
    await processor.handle_batch([message(stale("EURUSD"), "pricing-log")])
    await flusher(pool, redis, snapshot).flush_due(later_ms(11))

    await processor.handle_batch([message(stale("EURUSD"), "pricing-log")])
    await flusher(pool, redis, snapshot).flush_due(later_ms(22))

    assert [row["count"] for row in await summaries(pool)] == [1, 1]


async def test_grouped_rule_does_not_create_dedup_alerts(pool, redis, make_processor) -> None:
    await make_processor().handle_batch([message(stale("EURUSD"), "pricing-log")] * 3)

    assert await pool.fetchval("SELECT count(*) FROM alerts WHERE rule_id = $1", RULE_ID) == 0


async def test_window_survives_a_long_database_outage(
    pool, redis, make_processor, snapshot
) -> None:
    await make_processor().handle_batch([message(stale("EURUSD"), "pricing-log")])
    worker = flusher(pool, redis, snapshot)
    now = later_ms(11)
    claim_args = [RETRY_AFTER_MS, RETRY_AFTER_MS + 60_000]
    [raw] = await worker._claim(keys=[DEADLINES_KEY], args=[now, 100, *claim_args])
    flushing = raw.decode()

    for _ in range(10):  # Postgres down for 5 minutes: every retry claims and fails again
        await redis.pexpire(flushing, 1_000)  # as if the TTL had almost run out
        now += RETRY_AFTER_MS + 1
        assert await worker._claim(keys=[DEADLINES_KEY], args=[now, 100, *claim_args]) == [raw]
        assert await redis.pttl(flushing) > RETRY_AFTER_MS

    assert await worker._flush_window(flushing) == 1
    assert len(await summaries(pool)) == 1
