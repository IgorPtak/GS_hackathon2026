"""Fixtures: a throwaway Postgres schema per test and Redis DB 12, so parallel work is safe."""

import uuid
from collections.abc import AsyncIterator

import asyncpg
import pytest
from alerting_core.connections import create_database_pool
from alerting_core.settings import Settings
from redis.asyncio import Redis

BASE_URL = "postgresql://alerting:change-me-local-only@localhost:5432/alerting"
REDIS_URL = "redis://localhost:6379/12"

_DDL = """
CREATE TABLE config_documents (
    kind text NOT NULL, id text NOT NULL, team text, document jsonb NOT NULL, yaml text NOT NULL,
    version int NOT NULL DEFAULT 1 CHECK (version >= 1),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by jsonb, PRIMARY KEY (kind, id))
"""


@pytest.fixture
async def pool() -> AsyncIterator[asyncpg.Pool]:
    schema = f"t_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(BASE_URL)
    await admin.execute(f"CREATE SCHEMA {schema}")
    await admin.execute(f"SET search_path = {schema}")
    await admin.execute(_DDL)
    db_pool = await create_database_pool(Settings(database_url=f"{BASE_URL}?search_path={schema}"))
    try:
        yield db_pool
    finally:
        await db_pool.close()
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(REDIS_URL)
    try:
        yield client
    finally:
        await client.aclose()
