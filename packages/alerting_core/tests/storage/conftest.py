"""Storage tests run against a private Postgres database built from the migration."""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from alerting_contracts.alerts import Alert, AlertStatus
from alerting_core.connections import create_database_pool
from alerting_core.ids import new_uuid7
from alerting_core.settings import Settings
from alerting_core.storage.rows import ALERT_COLUMNS, alert_values

MIGRATION = Path(__file__).parents[4] / "deploy/postgres/migrations/0001_initial.sql"
TEST_DATABASE = "alerting_storage_test"


async def ensure_test_database(settings: Settings) -> str:
    """A private database built from the migration, so the shared stack's data is never touched."""
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
    await database_pool.execute(
        "TRUNCATE alerts, outbox, deliveries, audit_entries, action_runs, approval_requests"
    )
    yield database_pool
    await database_pool.close()


def make_alert(
    team: str = "rates",
    last_seen: datetime | None = None,
    status: AlertStatus = AlertStatus.open,
    alert_id: str | None = None,
) -> Alert:
    seen = last_seen or datetime.now(UTC)
    return Alert(
        id=alert_id or new_uuid7(),
        rule_id="limit-breach",
        team=team,
        schema_profile_id="trades",
        source_id="webhook",
        fingerprint="abc",
        severity="error",
        title="Rejected EUR 25000000",
        first_seen=seen,
        last_seen=seen,
        status=status,
        last_event={"amount": 25000000},
        updated_at=seen,
    )


InsertAlert = Callable[..., Awaitable[Alert]]


@pytest.fixture
def insert_alert(pool: asyncpg.Pool) -> InsertAlert:
    async def insert(**kwargs: object) -> Alert:
        alert = make_alert(**kwargs)  # type: ignore[arg-type]
        placeholders = ", ".join(f"${i + 1}" for i in range(len(ALERT_COLUMNS)))
        await pool.execute(
            f"INSERT INTO alerts ({', '.join(ALERT_COLUMNS)}) VALUES ({placeholders})",
            *[UUID(v) if i == 0 else v for i, v in enumerate(alert_values(alert))],
        )
        return alert

    return insert
