"""Read recent raw events from the `events` stream for rule preview and schema-profile tests.

Read-only `XRANGE`; never touches consumer groups. Entries that are not a valid `EventEnvelope`
are skipped and counted so the caller can warn instead of silently under-reporting.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from alerting_contracts.events import EventEnvelope
from pydantic import ValidationError
from redis.asyncio import Redis

from .logging import get_logger

log = get_logger(__name__)

EVENTS_STREAM = "events"
PAGE_SIZE = 1000


@dataclass(slots=True)
class EventRead:
    """Envelopes read oldest first, plus what was skipped or cut off."""

    envelopes: list[EventEnvelope] = field(default_factory=list)
    skipped_invalid: int = 0
    is_capped: bool = False


def _envelope_field(fields: dict[Any, Any]) -> bytes | str | None:
    value = fields.get(b"envelope")
    return value if value is not None else fields.get("envelope")


async def read_event_log(redis: Redis, since: datetime, max_events: int) -> EventRead:
    """Page through `XRANGE events <since ms>-0 +` (COUNT 1000) up to `max_events` envelopes."""
    since_utc = since.replace(tzinfo=UTC) if since.tzinfo is None else since
    cursor = f"{int(since_utc.timestamp() * 1000)}-0"
    result = EventRead()
    while True:
        entries = await redis.xrange(EVENTS_STREAM, min=cursor, max="+", count=PAGE_SIZE)
        if not entries:
            return result
        for entry_id, fields in entries:
            if len(result.envelopes) >= max_events:
                result.is_capped = True
                return result
            raw = _envelope_field(fields)
            try:
                if raw is None:
                    raise ValueError("entry has no envelope field")
                result.envelopes.append(EventEnvelope.model_validate_json(raw))
            except (ValidationError, ValueError):
                result.skipped_invalid += 1
                log.warning("event_log_entry_skipped", extra={"entry_id": str(entry_id)})
        if len(entries) < PAGE_SIZE:
            return result
        last_id = entries[-1][0]
        last_text = last_id.decode() if isinstance(last_id, bytes) else last_id
        cursor = f"({last_text}"  # exclusive start (Redis >= 6.2)


async def read_events(redis: Redis, since: datetime, max_events: int) -> list[EventEnvelope]:
    """Valid envelopes since `since`, oldest first, at most `max_events`."""
    return (await read_event_log(redis, since, max_events)).envelopes
