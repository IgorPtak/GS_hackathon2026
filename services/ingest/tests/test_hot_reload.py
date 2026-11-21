"""Hot-reload of sources: lookups follow the registry and log tails start/stop per source."""

import asyncio

import pytest
import redis
from alerting_contracts.config import SourceConfig
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.ingest.main import create_app
from services.ingest.sources import LogTailSet
from services.ingest.tests.fake_registry import FakeRegistry

REDIS_URL = "redis://localhost:6379/15"


def webhook(source_id: str) -> SourceConfig:
    return SourceConfig(id=source_id, type="webhook")


def log_tail(source_id: str, path: str) -> SourceConfig:
    return SourceConfig(id=source_id, type="log_tail", settings={"path": path})


def test_new_source_is_accepted_and_removed_source_is_404() -> None:
    try:
        redis.Redis.from_url(REDIS_URL).ping()
    except redis.ConnectionError:
        pytest.skip("Redis not reachable on localhost:6379")
    registry = FakeRegistry({"a": webhook("a")})
    app = create_app(Settings(redis_url=REDIS_URL), registry)  # type: ignore[arg-type]
    with TestClient(app) as client:
        assert client.post("/api/v1/ingest/b", json={}).status_code == 404
        registry.set_sources({"a": webhook("a"), "b": webhook("b")})
        assert client.post("/api/v1/ingest/b", json={}).status_code == 202
        registry.set_sources({"a": webhook("a")})
        assert client.post("/api/v1/ingest/b", json={}).status_code == 404
        assert client.post("/api/v1/ingest/a", json={}).status_code == 202


async def test_log_tails_start_stop_and_restart_only_the_changed_one() -> None:
    started: list[tuple[str, str]] = []
    cancelled: list[str] = []

    async def start_tail(source: SourceConfig) -> None:
        started.append((source.id, str(source.settings["path"])))
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            cancelled.append(source.id)
            raise

    tails = LogTailSet(start_tail)
    tails.reconcile({"x": log_tail("x", "/a"), "y": log_tail("y", "/b"), "w": webhook("w")})
    await asyncio.sleep(0.01)
    assert tails.source_ids == ["x", "y"]
    assert sorted(started) == [("x", "/a"), ("y", "/b")]

    tails.reconcile({"x": log_tail("x", "/a2"), "y": log_tail("y", "/b")})
    await asyncio.sleep(0.01)
    assert cancelled == ["x"]
    assert sorted(started) == [("x", "/a"), ("x", "/a2"), ("y", "/b")]

    tails.reconcile({"x": log_tail("x", "/a2")})
    await asyncio.sleep(0.01)
    assert tails.source_ids == ["x"]
    assert cancelled == ["x", "y"]

    await tails.stop()
    assert tails.source_ids == []
    assert cancelled == ["x", "y", "x"]


async def test_quick_successive_restarts_leave_exactly_one_tail() -> None:
    running: set[str] = set()
    started: list[str] = []

    async def start_tail(source: SourceConfig) -> None:
        path = str(source.settings["path"])
        started.append(path)
        running.add(path)
        try:
            await asyncio.sleep(3600)
        finally:
            # A slow lock release keeps the old runner alive while the next reconcile arrives.
            await asyncio.sleep(0.02)
            running.discard(path)

    tails = LogTailSet(start_tail)
    tails.reconcile({"x": log_tail("x", "/a")})
    await asyncio.sleep(0.01)
    tails.reconcile({"x": log_tail("x", "/b")})
    await asyncio.sleep(0)
    tails.reconcile({"x": log_tail("x", "/c")})
    await asyncio.sleep(0.1)

    assert running == {"/c"}
    assert "/b" not in started

    await tails.stop()
    await asyncio.sleep(0.05)
    assert running == set()
