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
