"""DB-backed tests use a private database built from the migration (skipped without Postgres)."""

from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from alerting_core.connections import create_database_pool
from alerting_core.settings import Settings

ROOT = Path(__file__).parents[3]
MIGRATION = ROOT / "deploy/postgres/migrations/0001_initial.sql"
TEST_DATABASE = "alerting_runbook_runner_test"


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
    except (OSError, asyncpg.PostgresError):
        pytest.skip("Postgres on localhost:5432 is not running")
    database_pool = await create_database_pool(Settings(database_url=test_url))
    await database_pool.execute(
        "TRUNCATE alerts, outbox, deliveries, audit_entries, action_runs, approval_requests"
    )
    yield database_pool
    await database_pool.close()
