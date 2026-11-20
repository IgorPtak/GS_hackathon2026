"""Routes tagged `ops`: health and the raw event stream view."""

from typing import Annotated

import orjson
from alerting_contracts.events import EventEnvelope
from alerting_core.logging import get_logger
from fastapi import APIRouter, Query
from pydantic import ValidationError

from ..dependencies import RedisDep

log = get_logger(__name__)
router = APIRouter(tags=["ops"])

STREAM = "events"
BATCH = 500
# Entries scanned when filtering by source_id, so a quiet source cannot scan the whole stream.
SCAN_CAP = 5000


@router.get("/healthz")
async def get_health() -> dict[str, str]:
    """Liveness probe used by compose healthchecks."""
    return {"status": "ok"}


@router.get("/api/v1/events/recent")
async def list_recent_events(
    redis: RedisDep,
    source_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[EventEnvelope]:
    """Newest raw events from the events stream (XREVRANGE), optionally for one source."""
    found: list[EventEnvelope] = []
    scanned = 0
    cursor = "+"
    while len(found) < limit and scanned < (SCAN_CAP if source_id else limit):
        count = BATCH if source_id else limit
        entries = await redis.xrevrange(STREAM, max=cursor, min="-", count=count + 1)
        if cursor != "+":
            entries = entries[1:]  # max is inclusive: drop the entry already seen
        if not entries:
            break
        for entry_id, fields in entries:
            scanned += 1
            raw = fields.get(b"envelope", fields.get("envelope"))
            try:
                envelope = EventEnvelope.model_validate(orjson.loads(raw))
            except (TypeError, ValueError, ValidationError):
                log.warning("events_recent_bad_entry", extra={"entry_id": str(entry_id)})
                continue
            if source_id is None or envelope.source_id == source_id:
                found.append(envelope)
                if len(found) == limit:
                    break
        cursor = entries[-1][0].decode() if isinstance(entries[-1][0], bytes) else entries[-1][0]
    return found
