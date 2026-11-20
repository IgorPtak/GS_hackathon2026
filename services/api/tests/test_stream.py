"""SSE endpoint with a fake pubsub."""

import asyncio
from typing import Any

import orjson
import pytest
from alerting_core.settings import Settings

from services.api.dependencies import get_redis
from services.api.main import create_app
from services.api.routers import stream as stream_router


def message(event_type: str, **extra: Any) -> dict[str, Any]:
    return {"type": "message", "data": orjson.dumps({"type": event_type, "at": "x", **extra})}


class FakePubSub:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = list(messages)
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.extend(channels)

    async def unsubscribe(self, *channels: str) -> None:
        self.unsubscribed.extend(channels)

    async def aclose(self) -> None:
        self.closed = True

    async def get_message(
        self,
        ignore_subscribe_messages: bool = False,
        timeout: float = 0,  # noqa: ASYNC109 - mirrors redis-py
    ):
        if self.messages:
            return self.messages.pop(0)
        await asyncio.sleep(0.01)
        return None


class FakeRedis:
    def __init__(self, pubsub: FakePubSub) -> None:
        self._pubsub = pubsub

    def pubsub(self) -> FakePubSub:
        return self._pubsub


async def asgi_get(app: Any, path: str, query: str, until: Any) -> tuple[dict[str, Any], str]:
    """Run one GET through the ASGI app, then send http.disconnect once `until(text)` holds."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": query.encode(),
        "headers": [],
        "server": ("test", 80),
        "client": ("test", 1),
        "scheme": "http",
    }
    disconnect = asyncio.Event()
    start: dict[str, Any] = {}
    chunks: list[str] = []

    async def receive() -> dict[str, Any]:
        await disconnect.wait()
        return {"type": "http.disconnect"}

    async def send(event: dict[str, Any]) -> None:
        if event["type"] == "http.response.start":
            start.update(event)
        elif event["type"] == "http.response.body":
            chunks.append(event.get("body", b"").decode())
            if until("".join(chunks)):
                disconnect.set()

    async with asyncio.timeout(5):
        await app(scope, receive, send)
    headers = {k.decode(): v.decode() for k, v in start["headers"]}
    return headers, "".join(chunks)


async def test_two_events_heartbeat_headers_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream_router, "HEARTBEAT_SECONDS", 0.05)
    pubsub = FakePubSub([message("alert.created"), message("notification", title="t")])
    app = create_app(Settings())
    app.dependency_overrides[get_redis] = lambda: FakeRedis(pubsub)

    headers, body = await asgi_get(app, "/api/v1/stream", "team=rates", lambda t: ": ping" in t)

    assert headers["content-type"].startswith("text/event-stream")
    assert headers["cache-control"] == "no-cache" and headers["x-accel-buffering"] == "no"
    frames = [f for f in body.split("\n\n") if f.startswith("event:")]
    assert len(frames) == 2
    names = []
    for frame in frames:
        event_line, data_line = frame.split("\n")
        assert event_line.startswith("event: ") and data_line.startswith("data: ")
        names.append(event_line.removeprefix("event: "))
        assert orjson.loads(data_line.removeprefix("data: "))["type"] == names[-1]
    assert names == ["alert.created", "notification"]
    assert ": ping" in body
    assert pubsub.subscribed == ["alerts.team.rates", "broadcast"]
    assert pubsub.unsubscribed == pubsub.subscribed and pubsub.closed


async def test_malformed_message_is_skipped() -> None:
    pubsub = FakePubSub([{"type": "message", "data": b"not json"}, message("alert.updated")])
    gen = stream_router.stream_frames(pubsub, ["c"], heartbeat_seconds=60, poll_seconds=0.01)
    frames = [await anext(gen), await anext(gen)]
    await gen.aclose()
    assert frames[1].startswith("event: alert.updated\n")
    assert pubsub.closed


def test_team_is_required() -> None:
    from fastapi.testclient import TestClient

    app = create_app(Settings())
    app.dependency_overrides[get_redis] = lambda: FakeRedis(FakePubSub([]))
    assert TestClient(app).get("/api/v1/stream").status_code == 422
