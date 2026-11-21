"""Retention trimming of the `events` stream that never outruns a consumer group."""

import asyncio
import time
from contextlib import suppress

from alerting_core.logging import get_logger
from redis.asyncio import Redis
from redis.exceptions import RedisError, ResponseError

log = get_logger(__name__)

EVENTS_STREAM = "events"
# Entries older than this are trimmed once every group has delivered and acked them.
EVENTS_RETENTION_MS = 2 * 60 * 60 * 1000
TRIM_INTERVAL_SECONDS = 60.0

StreamId = tuple[int, int]


def parse_stream_id(value: bytes | str) -> StreamId:
    """`<ms>-<seq>` as a tuple, so ids compare numerically ("10-0" > "9-0")."""
    text = value.decode() if isinstance(value, bytes) else value
    milliseconds, _, sequence = text.partition("-")
    return int(milliseconds), int(sequence or 0)


def format_stream_id(stream_id: StreamId) -> str:
    """Inverse of `parse_stream_id`."""
    return f"{stream_id[0]}-{stream_id[1]}"


def _is_missing_key(error: ResponseError) -> bool:
    return "no such key" in str(error).lower()


async def compute_trim_id(redis: Redis, stream: str, now_ms: int) -> StreamId | None:
    """Lowest id that may still be needed: min(now - retention, every group's frontier).

    A group's frontier is its oldest pending id (delivered, not acked) or, without pending
    entries, its last-delivered-id. Returns None when the round must be skipped: the stream
    does not exist (quietly) or Redis could not describe the groups (logged).
    """
    candidates: list[StreamId] = [(max(now_ms - EVENTS_RETENTION_MS, 0), 0)]
    try:
        groups = await redis.xinfo_groups(stream)
        for group in groups:
            candidates.append(parse_stream_id(group["last-delivered-id"]))
            pending = await redis.xpending(stream, group["name"])
            if pending["pending"] and pending["min"] is not None:
                candidates.append(parse_stream_id(pending["min"]))
    except ResponseError as error:
        if _is_missing_key(error):
            return None
        log.warning("events_trim_skipped", extra={"stream": stream, "error": str(error)})
        return None
    except RedisError as error:
        log.warning("events_trim_skipped", extra={"stream": stream, "error": str(error)})
        return None
    return min(candidates)


async def trim_events_once(redis: Redis, stream: str = EVENTS_STREAM) -> StreamId | None:
    """One trim round; returns the MINID used, or None when the round was skipped."""
    trim_id = await compute_trim_id(redis, stream, int(time.time() * 1000))
    if trim_id is None:
        return None
    # MINID keeps entries >= trim_id, so the oldest pending entry itself survives.
    await redis.xtrim(stream, minid=format_stream_id(trim_id), approximate=True)
    return trim_id


async def trim_events(redis: Redis, stop: asyncio.Event) -> None:
    """Trim `events` every minute, never past the slowest consumer group."""
    while not stop.is_set():
        try:
            await trim_events_once(redis)
        except RedisError:
            log.exception("events_trim_failed")
        with suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=TRIM_INTERVAL_SECONDS)
