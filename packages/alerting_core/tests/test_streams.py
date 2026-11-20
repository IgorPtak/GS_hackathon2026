"""StreamConsumer failure semantics against a real Redis (`docker compose up -d redis`)."""

import asyncio
from collections.abc import AsyncIterator

import pytest
from alerting_core.streams import (
    BatchFailures,
    StreamConsumer,
    StreamMessage,
    dead_letter_stream,
    default_consumer_name,
)
from redis.asyncio import Redis

STREAM = "test-events"
GROUP = "test-processors"
IDLE_SECONDS = 0.05


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url("redis://localhost:6379/13")
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis on localhost:6379 is not running (docker compose up -d redis)")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


class RecordingHandler:
    """Records every batch; fails the entries whose `kind` field is in `failing_kinds`."""

    def __init__(self, failing_kinds: set[bytes] = frozenset(), raises: bool = False) -> None:
        self.batches: list[list[StreamMessage]] = []
        self._failing_kinds = failing_kinds
        self._raises = raises

    async def __call__(self, messages: list[StreamMessage]) -> BatchFailures:
        self.batches.append(messages)
        if self._raises:
            raise RuntimeError("handler crashed")
        return {m.id: "boom" for m in messages if m.fields.get(b"kind") in self._failing_kinds}

    @property
    def seen(self) -> list[StreamMessage]:
        return [message for batch in self.batches for message in batch]


def make_consumer(redis: Redis, handler: RecordingHandler, name: str = "c1") -> StreamConsumer:
    return StreamConsumer(
        redis,
        STREAM,
        GROUP,
        name,
        handler,
        block_ms=10,
        min_idle_seconds=IDLE_SECONDS,
        claim_interval_seconds=0.0,
        max_deliveries=5,
    )


async def add_entries(redis: Redis, *kinds: bytes) -> list[str]:
    return [(await redis.xadd(STREAM, {b"kind": kind})).decode() for kind in kinds]


async def pending_count(redis: Redis) -> int:
    return (await redis.xpending(STREAM, GROUP))["pending"]


async def test_entries_are_acknowledged_after_handler_success(redis: Redis) -> None:
    handler = RecordingHandler()
    consumer = make_consumer(redis, handler)
    await consumer.ensure_group()
    ids = await add_entries(redis, b"a", b"b", b"c")

    assert await consumer.read_once() == 3

    assert [m.id for m in handler.seen] == ids
    assert all(m.delivery_count == 1 for m in handler.seen)
    assert await pending_count(redis) == 0


async def test_entries_added_before_group_creation_are_read(redis: Redis) -> None:
    await add_entries(redis, b"early")
    handler = RecordingHandler()
    consumer = make_consumer(redis, handler)
    await consumer.ensure_group()
    await consumer.ensure_group()  # idempotent

    assert await consumer.read_once() == 1


async def test_failed_entries_stay_pending_and_others_are_acknowledged(redis: Redis) -> None:
    consumer = make_consumer(redis, RecordingHandler(failing_kinds={b"bad"}))
    await consumer.ensure_group()
    _, bad_id, _ = await add_entries(redis, b"ok", b"bad", b"ok")

    await consumer.read_once()

    pending = await redis.xpending_range(STREAM, GROUP, min="-", max="+", count=10)
    assert [entry["message_id"].decode() for entry in pending] == [bad_id]


async def test_handler_exception_leaves_whole_batch_pending(redis: Redis) -> None:
    consumer = make_consumer(redis, RecordingHandler(raises=True))
    await consumer.ensure_group()
    await add_entries(redis, b"a", b"b")

    await consumer.read_once()

    assert await pending_count(redis) == 2


async def test_idle_entries_of_a_dead_consumer_are_claimed_by_another(redis: Redis) -> None:
    crashed = make_consumer(redis, RecordingHandler(raises=True), name="crashed")
    await crashed.ensure_group()
    ids = await add_entries(redis, b"a", b"b")
    await crashed.read_once()

    survivor_handler = RecordingHandler()
    survivor = make_consumer(redis, survivor_handler, name="survivor")
    assert await survivor.reclaim_idle() == 0  # not idle long enough yet
    await asyncio.sleep(IDLE_SECONDS * 2)

    assert await survivor.reclaim_idle() == 2
    assert [m.id for m in survivor_handler.seen] == ids
    assert all(m.delivery_count == 2 for m in survivor_handler.seen)
    assert await pending_count(redis) == 0


async def test_poison_entry_goes_to_dead_letter_after_max_deliveries(redis: Redis) -> None:
    handler = RecordingHandler(failing_kinds={b"poison"})
    consumer = make_consumer(redis, handler)
    await consumer.ensure_group()
    [poison_id] = await add_entries(redis, b"poison")

    await consumer.read_once()
    for _ in range(10):
        await asyncio.sleep(IDLE_SECONDS * 2)
        await consumer.reclaim_idle()
        if await pending_count(redis) == 0:
            break

    assert len(handler.seen) == 5  # 1 read + 4 claims; the 5th failure triggers the DLQ
    assert await pending_count(redis) == 0
    [(_, fields)] = await redis.xrange(dead_letter_stream(STREAM))
    assert fields[b"kind"] == b"poison"
    assert fields[b"error"] == b"boom"
    assert fields[b"attempts"] == b"5"
    assert poison_id in {m.id for m in handler.seen}


async def test_explicit_dead_letter_moves_entry_and_acknowledges_it(redis: Redis) -> None:
    async def reject_all(messages: list[StreamMessage]) -> BatchFailures:
        await consumer.dead_letter(messages, "invalid JSON")
        return {}

    consumer = StreamConsumer(redis, STREAM, GROUP, "c1", reject_all, block_ms=10)
    await consumer.ensure_group()
    await add_entries(redis, b"garbage")

    await consumer.read_once()

    assert await pending_count(redis) == 0
    [(_, fields)] = await redis.xrange(dead_letter_stream(STREAM))
    assert fields[b"error"] == b"invalid JSON"
    assert fields[b"attempts"] == b"1"


async def test_run_handles_entries_until_stopped(redis: Redis) -> None:
    handler = RecordingHandler()
    consumer = make_consumer(redis, handler)
    stop = asyncio.Event()
    task = asyncio.create_task(consumer.run(stop))
    await add_entries(redis, b"a", b"b")

    for _ in range(100):
        if len(handler.seen) == 2:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=2)

    assert len(handler.seen) == 2
    assert await pending_count(redis) == 0


def test_default_consumer_name_contains_service_and_pid() -> None:
    name = default_consumer_name("processor")
    assert name.startswith("processor-")
    assert name.rsplit("-", 1)[1].isdigit()


async def test_missing_group_is_recreated_by_run(redis: Redis) -> None:
    handler = RecordingHandler()
    consumer = make_consumer(redis, handler)
    stop = asyncio.Event()
    task = asyncio.create_task(consumer.run(stop))
    await add_entries(redis, b"before")
    for _ in range(100):
        if handler.seen:
            break
        await asyncio.sleep(0.01)

    # Redis restarted without persistence: stream and group are gone.
    await redis.delete(STREAM)
    await add_entries(redis, b"after")
    for _ in range(300):
        if len(handler.seen) == 2:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=3)

    assert [m.fields[b"kind"] for m in handler.seen] == [b"before", b"after"]


async def test_failing_reclaim_does_not_block_new_reads(
    redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    handler = RecordingHandler()
    consumer = make_consumer(redis, handler)

    async def broken_reclaim() -> int:
        raise ConnectionError("XPENDING failed")

    monkeypatch.setattr(consumer, "reclaim_idle", broken_reclaim)
    stop = asyncio.Event()
    task = asyncio.create_task(consumer.run(stop))
    await add_entries(redis, b"a")
    for _ in range(100):
        if handler.seen:
            break
        await asyncio.sleep(0.01)
    stop.set()
    await asyncio.wait_for(task, timeout=2)

    assert len(handler.seen) == 1


async def test_trimmed_poison_entry_is_acknowledged_without_dead_letter_copy(
    redis: Redis,
) -> None:
    consumer = make_consumer(redis, RecordingHandler(failing_kinds={b"poison"}))
    await consumer.ensure_group()
    [poison_id] = await add_entries(redis, b"poison")
    await consumer.read_once()
    await redis.xdel(STREAM, poison_id)

    for _ in range(10):
        await asyncio.sleep(IDLE_SECONDS * 2)
        await consumer.reclaim_idle()
        if await pending_count(redis) == 0:
            break

    assert await pending_count(redis) == 0
    assert await redis.xlen(dead_letter_stream(STREAM)) == 0
