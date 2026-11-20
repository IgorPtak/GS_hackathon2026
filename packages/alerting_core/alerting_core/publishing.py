"""Best-effort Redis pub/sub for the live feed (see contracts/storage.md)."""

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
    except RedisError:
        # Pub/sub is best effort: the UI refetches over REST after reconnecting.
        log.warning("publish_failed", extra={"channel": channel})


async def publish_team_event(redis: Redis, team: str, event: BaseModel) -> None:
    """Publish an SseEvent model to `alerts.team.<team>`; never raises."""
    await _publish(redis, team_channel(team), event)


async def publish_broadcast(redis: Redis, event: BaseModel) -> None:
    """Publish an SseEvent model to `broadcast`; never raises."""
    await _publish(redis, BROADCAST_CHANNEL, event)


async def publish_alert_change(redis: Redis, alert: Alert, audit_entries: list[AuditEntry]) -> None:
    """After commit: publish `alert.updated` plus one `audit.appended` per entry to the team."""
    now = datetime.now(UTC)
    await publish_team_event(redis, alert.team, AlertUpdatedEvent(at=now, alert=alert))
    for entry in audit_entries:
        await publish_team_event(redis, alert.team, AuditAppendedEvent(at=now, entry=entry))
