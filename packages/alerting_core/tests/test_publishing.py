"""Pub/sub helpers against real Redis (DB 7)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import orjson
import pytest
from alerting_contracts.alerts import Alert, AuditEntry, AuditVerb
from alerting_contracts.common import Actor
from alerting_contracts.sse import AlertUpdatedEvent, AuditAppendedEvent, ConfigChangedEvent
from alerting_core.ids import new_uuid7
from alerting_core.publishing import (
    publish_alert_change,
    publish_broadcast,
    publish_team_event,
    publish_team_events,
)
from redis.asyncio import Redis

REDIS_URL = "redis://localhost:6379/7"


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(REDIS_URL)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis on localhost:6379 is not running")
    yield client
    await client.aclose()


def sample_alert() -> Alert:
    now = datetime.now(UTC)
    return Alert(
        id=new_uuid7(),
        rule_id="r",
        team="rates",
        schema_profile_id="p",
        source_id="s",
        fingerprint="f",
        severity="error",
        title="t",
        first_seen=now,
        last_seen=now,
        last_event={},
        updated_at=now,
    )


async def collect(redis: Redis, channel: str, count: int, publish) -> list[dict]:
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    await pubsub.get_message(timeout=1)  # subscribe confirmation
    await publish()
    messages: list[dict] = []
    async with asyncio.timeout(3):
        while len(messages) < count:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
            if message:
                messages.append(orjson.loads(message["data"]))
    await pubsub.aclose()
    return messages


async def test_publish_team_event_sends_contract_json(redis: Redis) -> None:
    event = AlertUpdatedEvent(at=datetime.now(UTC), alert=sample_alert())
    [payload] = await collect(
        redis, "alerts.team.rates", 1, lambda: publish_team_event(redis, "rates", event)
    )
    assert AlertUpdatedEvent.model_validate(payload) == event
    assert payload["type"] == "alert.updated"


async def test_publish_broadcast_uses_broadcast_channel(redis: Redis) -> None:
    event = ConfigChangedEvent(at=datetime.now(UTC), kind="rule", id="r", version=2)
    [payload] = await collect(redis, "broadcast", 1, lambda: publish_broadcast(redis, event))
    assert payload["type"] == "config.changed"


async def test_publish_alert_change_sends_update_and_audit(redis: Redis) -> None:
    alert = sample_alert()
    entry = AuditEntry(
        id=1,
        alert_id=alert.id,
        at=datetime.now(UTC),
        actor=Actor(id="anna"),
        verb=AuditVerb.alert_acknowledged,
    )
    payloads = await collect(
        redis, "alerts.team.rates", 2, lambda: publish_alert_change(redis, alert, [entry])
    )
    assert [p["type"] for p in payloads] == ["alert.updated", "audit.appended"]
    assert AuditAppendedEvent.model_validate(payloads[1]).entry == entry


async def test_publish_never_raises_when_redis_is_unreachable() -> None:
    dead = Redis.from_url("redis://localhost:1/0", socket_connect_timeout=0.2)
    event = ConfigChangedEvent(at=datetime.now(UTC), kind="rule", id="r", version=1)
    await publish_team_event(dead, "rates", event)
    await publish_broadcast(dead, event)
    await dead.aclose()


async def test_publish_swallows_os_errors() -> None:
    class BrokenRedis:
        async def publish(self, channel: str, data: bytes) -> int:
            raise ConnectionResetError("boom")

    event = ConfigChangedEvent(at=datetime.now(UTC), kind="rule", id="r", version=1)
    await publish_team_event(BrokenRedis(), "rates", event)  # type: ignore[arg-type]


async def test_publish_team_events_batches_into_one_pipeline(redis: Redis) -> None:
    alert = sample_alert()
    now = datetime.now(UTC)
    entry = AuditEntry(
        id=1, alert_id=alert.id, at=now, actor=Actor(id="anna"), verb=AuditVerb.alert_acknowledged
    )
    events = [AlertUpdatedEvent(at=now, alert=alert), AuditAppendedEvent(at=now, entry=entry)]

    payloads = await collect(
        redis, "alerts.team.rates", 2, lambda: publish_team_events(redis, "rates", events)
    )

    assert [p["type"] for p in payloads] == ["alert.updated", "audit.appended"]
    assert AlertUpdatedEvent.model_validate(payloads[0]).alert == alert
    assert AuditAppendedEvent.model_validate(payloads[1]).entry == entry


async def test_publish_team_events_uses_non_transactional_pipeline_and_skips_empty() -> None:
    calls: list[tuple[bool, list[tuple[str, bytes]], int]] = []

    class SpyPipeline:
        def __init__(self, transaction: bool) -> None:
            self._transaction = transaction
            self._items: list[tuple[str, bytes]] = []
            self._executes = 0

        async def __aenter__(self) -> "SpyPipeline":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def publish(self, channel: str, data: bytes) -> "SpyPipeline":
            self._items.append((channel, data))
            return self

        async def execute(self) -> list[int]:
            self._executes += 1
            calls.append((self._transaction, list(self._items), self._executes))
            return [1] * len(self._items)

    class SpyRedis:
        def pipeline(self, *, transaction: bool = True) -> SpyPipeline:
            return SpyPipeline(transaction)

    spy = SpyRedis()
    await publish_team_events(spy, "rates", [])  # type: ignore[arg-type]
    assert calls == []

    now = datetime.now(UTC)
    events = [
        ConfigChangedEvent(at=now, kind="rule", id="r1", version=1),
        ConfigChangedEvent(at=now, kind="rule", id="r2", version=2),
    ]
    await publish_team_events(spy, "rates", events)  # type: ignore[arg-type]
    assert len(calls) == 1
    assert calls[0][0] is False
    assert [ch for ch, _ in calls[0][1]] == ["alerts.team.rates", "alerts.team.rates"]
    assert calls[0][2] == 1


async def test_publish_team_events_swallows_pipeline_errors() -> None:
    class BrokenPipeline:
        async def __aenter__(self) -> "BrokenPipeline":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        def publish(self, channel: str, data: bytes) -> "BrokenPipeline":
            return self

        async def execute(self) -> list[int]:
            raise ConnectionResetError("boom")

    class BrokenPipelineRedis:
        def pipeline(self, *, transaction: bool = True) -> BrokenPipeline:
            return BrokenPipeline()

    event = ConfigChangedEvent(at=datetime.now(UTC), kind="rule", id="r", version=1)
    await publish_team_events(BrokenPipelineRedis(), "rates", [event])  # type: ignore[arg-type]
