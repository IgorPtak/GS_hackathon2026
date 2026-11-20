"""read_events against a real Redis (DB 3; `docker compose up -d redis`)."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from alerting_contracts.events import EventEnvelope
from alerting_core.event_log import read_event_log, read_events
from redis.asyncio import Redis

NOW = datetime.now(UTC)


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url("redis://localhost:6379/3")
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis on localhost:6379 is not running (docker compose up -d redis)")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


def envelope_json(index: int) -> str:
    return EventEnvelope(
        event_id=f"E{index:08d}",
        source_id="s",
        source_type="webhook",
        received_at=NOW,
        payload={"n": index},
    ).model_dump_json()


async def add(redis: Redis, count: int, start_ms: int, field: str = "envelope", value=None) -> None:  # noqa: ANN001
    async with redis.pipeline(transaction=False) as pipe:
        for index in range(count):
            pipe.xadd("events", {field: value or envelope_json(index)}, id=f"{start_ms + index}-0")
        await pipe.execute()


async def test_pages_over_more_than_a_thousand_entries_in_order(redis: Redis) -> None:
    base = int((NOW - timedelta(minutes=5)).timestamp() * 1000)
    await add(redis, 2500, base)

    envelopes = await read_events(redis, NOW - timedelta(minutes=10), 10_000)

    assert len(envelopes) == 2500
    assert [e.payload["n"] for e in envelopes[:3]] == [0, 1, 2]


async def test_since_excludes_older_entries(redis: Redis) -> None:
    old = int((NOW - timedelta(hours=2)).timestamp() * 1000)
    recent = int((NOW - timedelta(minutes=1)).timestamp() * 1000)
    await add(redis, 5, old)
    await add(redis, 3, recent)

    assert len(await read_events(redis, NOW - timedelta(hours=1), 100)) == 3


async def test_max_events_caps_and_is_reported(redis: Redis) -> None:
    base = int((NOW - timedelta(minutes=5)).timestamp() * 1000)
    await add(redis, 1500, base)

    result = await read_event_log(redis, NOW - timedelta(minutes=10), 1200)

    assert len(result.envelopes) == 1200
    assert result.is_capped


async def test_exactly_max_events_is_not_capped(redis: Redis) -> None:
    base = int((NOW - timedelta(minutes=5)).timestamp() * 1000)
    await add(redis, 10, base)

    result = await read_event_log(redis, NOW - timedelta(minutes=10), 10)

    assert len(result.envelopes) == 10
    assert not result.is_capped


async def test_invalid_entries_are_skipped_and_counted(redis: Redis) -> None:
    base = int((NOW - timedelta(minutes=5)).timestamp() * 1000)
    await add(redis, 3, base)
    await add(redis, 1, base + 10, value="{not json")
    await add(redis, 1, base + 20, field="other")
    await add(redis, 1, base + 30, value='{"event_id": 1}')

    result = await read_event_log(redis, NOW - timedelta(minutes=10), 100)

    assert len(result.envelopes) == 3
    assert result.skipped_invalid == 3
