"""Unknown-schema inbox: events no specific profile recognised, one sample per key shape."""

from datetime import datetime

from alerting_contracts.api import UnknownSchemaSample
from alerting_contracts.sse import UnknownSchemaDetectedEvent
from alerting_core.events import key_paths, shape_hash
from alerting_core.publishing import publish_broadcast
from redis.asyncio import Redis

from .evaluation import EventOutcome


def collect_unknown_samples(outcomes: list[EventOutcome]) -> list[UnknownSchemaSample]:
    """One sample per shape in this batch, counting its events; the latest event is the sample."""
    samples: dict[str, UnknownSchemaSample] = {}
    for outcome in outcomes:
        if not outcome.is_unknown_shape:
            continue
        payload = outcome.envelope.payload
        digest = shape_hash(payload)
        seen = outcome.envelope.received_at
        current = samples.get(digest)
        samples[digest] = UnknownSchemaSample(
            shape_hash=digest,
            source_id=outcome.envelope.source_id,
            key_paths=current.key_paths if current else key_paths(payload),
            sample_event=payload,
            event_count=(current.event_count if current else 0) + 1,
            first_seen=current.first_seen if current else seen,
            last_seen=seen,
        )
    return list(samples.values())


async def publish_new_samples(
    redis: Redis, samples: list[UnknownSchemaSample], now: datetime
) -> None:
    """Announce each new shape once on `broadcast` (best effort, after commit)."""
    for sample in samples:
        await publish_broadcast(redis, UnknownSchemaDetectedEvent(at=now, sample=sample))
