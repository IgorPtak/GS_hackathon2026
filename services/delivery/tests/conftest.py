"""Delivery worker tests against the real Postgres and Redis, with a scripted channel plugin."""

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from types import MappingProxyType
from typing import Any

import asyncpg
import httpx
import pytest
from alerting_contracts.alerts import DeliveryJob
from alerting_core.config.loader import load_config_directory
from alerting_core.config.registry import ConfigSnapshot
from alerting_core.connections import create_database_pool
from alerting_core.settings import Settings
from alerting_core.streams import StreamMessage
from redis.asyncio import Redis

from plugins.channels.base import ChannelContext, ChannelPlugin
from services.delivery.worker import DeliveryWorker

ROOT = Path(__file__).parents[3]
MIGRATION = ROOT / "deploy/postgres/migrations/0001_initial.sql"
TEST_DATABASE = "alerting_delivery_test"
REDIS_URL = "redis://localhost:6379/4"


class FakeRegistry:
    def __init__(self, snapshot: ConfigSnapshot) -> None:
        self.snapshot = snapshot


class ScriptedPlugin(ChannelPlugin):
    """Raises the queued exceptions in order, then succeeds; records every send."""

    def __init__(self) -> None:
        self.failures: list[Exception] = []
        self.sent: list[DeliveryJob] = []

    async def send(self, job, recipient, config, context) -> None:  # noqa: ANN001
        if self.failures:
            raise self.failures.pop(0)
        self.sent.append(job)


def load_snapshot() -> ConfigSnapshot:
    documents: dict[str, dict[str, Any]] = {}
    for document in load_config_directory(ROOT / "config").documents:
        documents.setdefault(document.kind, {})[document.id] = document.model
    return ConfigSnapshot(MappingProxyType({k: MappingProxyType(v) for k, v in documents.items()}))


def email_job(delivery_id: int = 1, **update: Any) -> DeliveryJob:
    alert_id = str(uuid.uuid4())
    job = DeliveryJob.model_validate(
        {
            "delivery_id": delivery_id,
            "alert_id": alert_id,
            "team": "rates",
            "recipient_id": "anna",
            "channel_id": "email",
            "channel_type": "email",
            "purpose": "alert",
            "content": {
                "title": "Rejected EUR 25000000 — LIMIT_BREACH",
                "severity": "error",
                "alert_url": f"http://localhost:5173/alerts/{alert_id}",
            },
        }
    )
    return job.model_copy(update=update)


def stream_message(job: DeliveryJob | bytes, entry_id: str = "1-0") -> StreamMessage:
    body = job if isinstance(job, bytes) else job.model_dump_json().encode()
    return StreamMessage(id=entry_id, fields={b"job": body}, delivery_count=1)


async def _ensure_test_database(settings: Settings) -> str:
    admin = await asyncpg.connect(settings.database_url)
    try:
        exists = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DATABASE)
        if not exists:
            await admin.execute(f"CREATE DATABASE {TEST_DATABASE}")
    finally:
        await admin.close()
    test_url = settings.database_url.rsplit("/", 1)[0] + f"/{TEST_DATABASE}"
    connection = await asyncpg.connect(test_url)
    try:
        await connection.execute(MIGRATION.read_text())
    finally:
        await connection.close()
    return test_url


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    try:
        test_url = await _ensure_test_database(Settings())
    except OSError:
        pytest.skip("Postgres on localhost:5432 is not running")
    database_pool = await create_database_pool(Settings(database_url=test_url))
    await database_pool.execute("TRUNCATE deliveries, outbox, audit_entries")
    yield database_pool
    await database_pool.close()


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(REDIS_URL)
    try:
        await client.ping()
    except Exception:
        pytest.skip("Redis on localhost:6379 is not running")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


@pytest.fixture
def plugin(monkeypatch: pytest.MonkeyPatch) -> ScriptedPlugin:
    scripted = ScriptedPlugin()
    monkeypatch.setattr("services.delivery.worker.get_channel_plugin", lambda _type: scripted)
    return scripted


@pytest.fixture
async def worker(pool, redis, plugin) -> AsyncIterator[DeliveryWorker]:  # noqa: ANN001
    async with httpx.AsyncClient() as http:
        context = ChannelContext(redis=redis, http=http, settings=Settings(), database=pool)
        yield DeliveryWorker(pool, redis, FakeRegistry(load_snapshot()), context)  # type: ignore[arg-type]
