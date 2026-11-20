"""Processor tests against the real Postgres and Redis (`docker compose up -d postgres redis`).

A private database built from the migration keeps the compose processor and relay away from
the rows these tests write.
"""

import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from types import MappingProxyType
from typing import Any

import asyncpg
import orjson
import pytest
from alerting_contracts.events import EventEnvelope
from alerting_core.config.loader import load_config_directory
from alerting_core.config.registry import ConfigSnapshot
from alerting_core.connections import create_database_pool
from alerting_core.ids import new_uuid7
from alerting_core.settings import Settings
from alerting_core.streams import StreamMessage
from redis.asyncio import Redis

from services.processor.batch import EventProcessor
from services.processor.folds import FoldTracker

ROOT = Path(__file__).parents[3]
MIGRATION = ROOT / "deploy/postgres/migrations/0001_initial.sql"
FIXTURES = ROOT / "contracts/fixtures/events"
TEST_DATABASE = "alerting_processor_test"
REDIS_URL = "redis://localhost:6379/5"


class FakeRegistry:
    """The two members EventProcessor uses: the snapshot and the reload callbacks."""

    def __init__(self, snapshot: ConfigSnapshot) -> None:
        self.snapshot = snapshot
        self.on_reload: list[Callable[[ConfigSnapshot], None]] = []


def load_snapshot() -> ConfigSnapshot:
    result = load_config_directory(ROOT / "config")
    documents: dict[str, dict[str, Any]] = {}
    for document in result.documents:
        documents.setdefault(document.kind, {})[document.id] = document.model
    return ConfigSnapshot(
        documents=MappingProxyType({k: MappingProxyType(v) for k, v in documents.items()})
    )


def fixture_payload(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


_sequence = 0


def message(payload: dict[str, Any], source_id: str = "rates-oms") -> StreamMessage:
    global _sequence
    _sequence += 1
    envelope = EventEnvelope(
        event_id=new_uuid7(),
        source_id=source_id,
        source_type="webhook",
        received_at=datetime.now(UTC),
        payload=payload,
    )
    fields = {b"envelope": orjson.dumps(envelope.model_dump(mode="json"))}
    return StreamMessage(id=f"{_sequence}-0", fields=fields, delivery_count=1)


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
    await database_pool.execute(
        "TRUNCATE alerts, outbox, deliveries, audit_entries, unknown_schema_samples"
    )
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


@pytest.fixture(scope="session")
def snapshot() -> ConfigSnapshot:
    return load_snapshot()


@pytest.fixture
def make_processor(
    pool: asyncpg.Pool, redis: Redis, snapshot: ConfigSnapshot
) -> Callable[[], EventProcessor]:
    def build() -> EventProcessor:
        folds = FoldTracker(pool, redis)
        return EventProcessor(pool, redis, FakeRegistry(snapshot), Settings(), folds)  # type: ignore[arg-type]

    return build
