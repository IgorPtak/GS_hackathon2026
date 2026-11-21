"""Real Postgres and Redis for relay tests (`docker compose up -d postgres redis`), else skipped."""

from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from alerting_core.connections import create_database_pool
from alerting_core.settings import Settings
from redis.asyncio import Redis

REDIS_URL = "redis://localhost:6379/11"
MIGRATION = Path(__file__).parents[3] / "deploy/postgres/migrations/0001_initial.sql"
TEST_DATABASE = "alerting_relay_test"


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


async def ensure_test_database(settings: Settings) -> str:
    """A private database built from the migration, so a running compose relay never steals rows."""
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
        await connection.execute(MIGRATION.read_text())  # idempotent
    finally:
        await connection.close()
    return test_url


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    try:
        test_url = await ensure_test_database(Settings())
    except OSError:
        pytest.skip("Postgres on localhost:5432 is not running")
    database_pool = await create_database_pool(Settings(database_url=test_url))
    await database_pool.execute("TRUNCATE outbox, deliveries, alerts, action_runs, audit_entries")
    yield database_pool
    await database_pool.close()
