"""Best-effort Redis pub/sub for the live feed (see contracts/storage.md)."""

from collections.abc import Iterable
from datetime import UTC, datetime

import orjson
from alerting_contracts.alerts import Alert, AuditEntry
from alerting_contracts.sse import AlertUpdatedEvent, AuditAppendedEvent
from pydantic import BaseModel
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .logging import get_logger

log = get_logger(__name__)
BROADCAST_CHANNEL = "broadcast"


def team_channel(team: str) -> str:
    """Pub/sub channel of one team."""
    return f"alerts.team.{team}"


async def _publish(redis: Redis, channel: str, event: BaseModel) -> None:
    try:
        await redis.publish(channel, orjson.dumps(event.model_dump(mode="json")))
    except (RedisError, OSError):  # OSError covers ConnectionError and timeouts
        # Pub/sub is best effort: the UI refetches over REST after reconnecting.
        log.warning("publish_failed", extra={"channel": channel})


async def publish_team_event(redis: Redis, team: str, event: BaseModel) -> None:
    """Publish an SseEvent model to `alerts.team.<team>`; never raises."""
    await _publish(redis, team_channel(team), event)


async def publish_team_events(redis: Redis, team: str, events: Iterable[BaseModel]) -> None:
    """Publish SseEvent models to `alerts.team.<team>` in one pipeline; never raises."""
    event_list = list(events)
    if not event_list:
        return
    channel = team_channel(team)
    try:
        async with redis.pipeline(transaction=False) as pipe:
            for event in event_list:
                pipe.publish(channel, event.model_dump_json().encode())
            await pipe.execute()
    except (RedisError, OSError):  # OSError covers ConnectionError and timeouts
        # Pub/sub is best effort: the UI refetches over REST after reconnecting.
        log.warning("publish_failed", extra={"channel": channel})


async def publish_broadcast(redis: Redis, event: BaseModel) -> None:
    """Publish an SseEvent model to `broadcast`; never raises."""
    await _publish(redis, BROADCAST_CHANNEL, event)


async def publish_alert_change(redis: Redis, alert: Alert, audit_entries: list[AuditEntry]) -> None:
    """After commit: publish `alert.updated` plus one `audit.appended` per entry to the team."""
    now = datetime.now(UTC)
    events: list[BaseModel] = [AlertUpdatedEvent(at=now, alert=alert)]
    events.extend(AuditAppendedEvent(at=now, entry=entry) for entry in audit_entries)
    await publish_team_events(redis, alert.team, events)
