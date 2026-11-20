"""Routes tagged `stream` in contracts/openapi.yaml (B-02): SSE from Redis pub/sub."""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Annotated, Any

import orjson
from alerting_core.logging import get_logger
from alerting_core.publishing import BROADCAST_CHANNEL, team_channel
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from redis.exceptions import RedisError

from ..dependencies import RedisDep

log = get_logger(__name__)
router = APIRouter(tags=["stream"])

HEARTBEAT_SECONDS = 15.0  # tests patch this
POLL_SECONDS = 1.0


def _frame(raw: bytes | str) -> str | None:
    """Format one pub/sub payload as an SSE frame; None if it is not an SseEvent."""
    try:
        event = orjson.loads(raw)
        event_type = event["type"]
    except (orjson.JSONDecodeError, KeyError, TypeError):
        log.warning("sse_message_skipped")
        return None
    data = raw.decode() if isinstance(raw, bytes) else raw
    return f"event: {event_type}\ndata: {data}\n\n"


async def stream_frames(
    pubsub: Any,
    channels: list[str],
    heartbeat_seconds: float,
    poll_seconds: float = POLL_SECONDS,
) -> AsyncIterator[str]:
    """Yield SSE frames and `: ping` heartbeats until cancelled; always cleans up the pubsub."""
    try:
        await pubsub.subscribe(*channels)
        yield ": connected\n\n"
        last_sent = time.monotonic()
        while True:  # ends by cancellation / aclose when the client disconnects
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll_seconds)
            if message is not None and message.get("type") == "message":
                frame = _frame(message["data"])
                if frame is not None:
                    last_sent = time.monotonic()
                    yield frame
                    continue
            if time.monotonic() - last_sent >= heartbeat_seconds:
                last_sent = time.monotonic()
                yield ": ping\n\n"
            elif message is None:
                await asyncio.sleep(0)
    finally:
        await asyncio.shield(_close(pubsub, channels))


async def _close(pubsub: Any, channels: list[str]) -> None:
    try:
        await pubsub.unsubscribe(*channels)
        await pubsub.aclose()
    except (RedisError, OSError) as error:
        log.warning("sse_cleanup_failed", extra={"error": repr(error)})


@router.get("/api/v1/stream")
async def stream_events(redis: RedisDep, team: Annotated[str, Query()]) -> StreamingResponse:
    """Server-sent events for one team plus the broadcast channel."""
    channels = [team_channel(team), BROADCAST_CHANNEL]
    return StreamingResponse(
        stream_frames(redis.pubsub(), channels, HEARTBEAT_SECONDS),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
