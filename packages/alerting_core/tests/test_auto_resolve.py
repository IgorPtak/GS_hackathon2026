"""Auto-resolve against the real Postgres and Redis (private DB, Redis DB 2)."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest
from alerting_contracts.alerts import Alert
from alerting_contracts.config import Rule
from alerting_core.auto_resolve import (
    CLAIM_LEASE_MS,
    ResolutionSignal,
    push_silence_deadlines,
    resolve_on_signals,
    resolve_silent_alerts,
)
from alerting_core.connections import create_database_pool
from alerting_core.dedup import dedup_count_key, dedup_key
from alerting_core.ids import new_uuid7
from alerting_core.settings import Settings
from alerting_core.storage.rows import ALERT_COLUMNS, alert_values
from redis.asyncio import Redis

MIGRATION = Path(__file__).parents[3] / "deploy/postgres/migrations/0001_initial.sql"
TEST_DATABASE = "alerting_resolve_test"
REDIS_URL = "redis://localhost:6379/2"


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
    await database_pool.execute("TRUNCATE alerts, outbox, deliveries, audit_entries")
    yield database_pool
    await database_pool.close()


@pytest.fixture
async def redis() -> AsyncIterator[Redis]:
    client = Redis.from_url(REDIS_URL)
    try:
        await client.ping()
    except OSError:
        pytest.skip("Redis on localhost:6379 is not running")
    await client.flushdb()
    yield client
    await client.flushdb()
    await client.aclose()


def make_rule(**auto_resolve: object) -> Rule:
    return Rule.model_validate(
        {
            "id": "r1",
            "team": "platform",
            "when": {"all": [{"field": "status", "op": "eq", "value": "firing"}]},
            "present": {"title": "t"},
            "auto_resolve": auto_resolve,
        }
    )


async def insert_alert(
    pool: asyncpg.Pool, first_seen: datetime, last_seen: datetime | None = None
) -> Alert:
    seen = last_seen or first_seen
    alert = Alert(
        id=new_uuid7(),
        rule_id="r1",
        team="platform",
        schema_profile_id="alertmanager",
        source_id="am",
        fingerprint="fp1",
        severity="error",
        title="t",
        first_seen=first_seen,
        last_seen=seen,
        last_event={},
        updated_at=seen,
    )
    placeholders = ", ".join(f"${i + 1}" for i in range(len(ALERT_COLUMNS)))
    await pool.execute(
        f"INSERT INTO alerts ({', '.join(ALERT_COLUMNS)}) VALUES ({placeholders})",
        *[UUID(v) if i == 0 else v for i, v in enumerate(alert_values(alert))],
    )
    return alert


def signal(at: datetime) -> ResolutionSignal:
    return ResolutionSignal(fingerprint="fp1", source_id="am", received_at=at)


def to_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


async def test_resolution_signal_resolves_audits_publishes_and_releases_key(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    now = datetime.now(UTC)
    alert = await insert_alert(pool, now - timedelta(minutes=1))
    await redis.set(dedup_key("r1", "fp1"), alert.id)
    pubsub = redis.pubsub()
    await pubsub.subscribe("alerts.team.platform")
    await pubsub.get_message(timeout=1)

    resolved = await resolve_on_signals(pool, redis, [signal(now)], {"r1": make_rule()})

    assert [a.id for a in resolved] == [alert.id]
    row = await pool.fetchrow(
        "SELECT status, resolution_reason, resolved_by FROM alerts WHERE id = $1::uuid", alert.id
    )
    assert (row["status"], row["resolution_reason"]) == ("resolved", "source_resolved")
    assert row["resolved_by"]["id"] == "system:processor"
    audit = await pool.fetch("SELECT verb FROM audit_entries WHERE alert_id = $1::uuid", alert.id)
    assert [r["verb"] for r in audit] == ["alert_resolved"]
    assert await redis.exists(dedup_key("r1", "fp1")) == 0
    message = await pubsub.get_message(timeout=1)
    assert message is not None and b"alert.updated" in message["data"]
    await pubsub.aclose()


async def test_rule_without_on_resolution_event_is_not_resolved(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    now = datetime.now(UTC)
    await insert_alert(pool, now - timedelta(minutes=1))
    rules = {"r1": make_rule(on_resolution_event=False)}
    assert await resolve_on_signals(pool, redis, [signal(now)], rules) == []


async def test_stale_signal_does_not_resolve_newer_alert(pool: asyncpg.Pool, redis: Redis) -> None:
    now = datetime.now(UTC)
    await insert_alert(pool, now)
    stale = signal(now - timedelta(minutes=5))
    assert await resolve_on_signals(pool, redis, [stale], {"r1": make_rule()}) == []


async def test_silent_alert_is_resolved(pool: asyncpg.Pool, redis: Redis) -> None:
    now = datetime.now(UTC)
    alert = await insert_alert(pool, now - timedelta(minutes=10))
    await push_silence_deadlines(redis, [(alert.id, to_ms(now - timedelta(minutes=5)))])
    rules = {"r1": make_rule(after_silence="5m")}

    resolved = await resolve_silent_alerts(pool, redis, rules, to_ms(now))

    assert [a.id for a in resolved] == [alert.id]
    reason = await pool.fetchval(
        "SELECT resolution_reason FROM alerts WHERE id = $1::uuid", alert.id
    )
    assert reason == "silence"


async def test_newer_event_moves_deadline_so_alert_stays_open(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    now = datetime.now(UTC)
    # last_seen is 1 minute ago, so with a 5 minute silence the real deadline is 4 minutes ahead.
    last_seen = now - timedelta(minutes=1)
    alert = await insert_alert(pool, now - timedelta(minutes=10), last_seen)
    await push_silence_deadlines(redis, [(alert.id, to_ms(now - timedelta(seconds=1)))])
    rules = {"r1": make_rule(after_silence="5m")}

    assert await resolve_silent_alerts(pool, redis, rules, to_ms(now)) == []

    status = await pool.fetchval("SELECT status FROM alerts WHERE id = $1::uuid", alert.id)
    assert status == "open"
    assert await redis.zscore("silence-deadlines", alert.id) == to_ms(last_seen) + 300_000


async def test_deadline_never_moves_back(redis: Redis) -> None:
    await push_silence_deadlines(redis, [("a", 2000)])
    await push_silence_deadlines(redis, [("a", 1000)])
    assert await redis.zscore("silence-deadlines", "a") == 2000


async def test_two_concurrent_resolvers_resolve_once(pool: asyncpg.Pool, redis: Redis) -> None:
    now = datetime.now(UTC)
    alert = await insert_alert(pool, now - timedelta(minutes=10))
    await push_silence_deadlines(redis, [(alert.id, to_ms(now - timedelta(minutes=5)))])
    rules = {"r1": make_rule(after_silence="5m")}

    results = await asyncio.gather(
        resolve_silent_alerts(pool, redis, rules, to_ms(now)),
        resolve_silent_alerts(pool, redis, rules, to_ms(now)),
    )

    assert sorted(len(r) for r in results) == [0, 1]
    count = await pool.fetchval(
        "SELECT count(*) FROM audit_entries WHERE alert_id = $1::uuid", alert.id
    )
    assert count == 1


async def test_rule_without_after_silence_drops_deadline(pool: asyncpg.Pool, redis: Redis) -> None:
    now = datetime.now(UTC)
    alert = await insert_alert(pool, now - timedelta(minutes=10))
    await push_silence_deadlines(redis, [(alert.id, 1)])

    assert await resolve_silent_alerts(pool, redis, {"r1": make_rule()}, to_ms(now)) == []
    assert await redis.zcard("silence-deadlines") == 0


async def test_signal_older_than_the_last_firing_event_does_not_resolve(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    now = datetime.now(UTC)
    await insert_alert(pool, now - timedelta(minutes=10), last_seen=now)  # fired again
    late = signal(now - timedelta(minutes=1))
    assert await resolve_on_signals(pool, redis, [late], {"r1": make_rule()}) == []


async def test_publish_failure_does_not_stop_other_resolutions(
    pool: asyncpg.Pool, redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    first = await insert_alert(pool, now - timedelta(minutes=2))
    second = await insert_alert(pool, now - timedelta(minutes=1))

    async def broken_publish(*_: object) -> None:
        raise ConnectionError("redis down")

    monkeypatch.setattr("alerting_core.auto_resolve.publish_alert_change", broken_publish)

    resolved = await resolve_on_signals(pool, redis, [signal(now)], {"r1": make_rule()})

    assert {a.id for a in resolved} == {first.id, second.id}


async def test_silence_resolution_is_audited_and_published(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    now = datetime.now(UTC)
    alert = await insert_alert(pool, now - timedelta(minutes=10))
    await push_silence_deadlines(redis, [(alert.id, to_ms(now) - 1)])
    pubsub = redis.pubsub()
    await pubsub.subscribe("alerts.team.platform")
    await pubsub.get_message(timeout=1)

    await resolve_silent_alerts(pool, redis, {"r1": make_rule(after_silence="5m")}, to_ms(now))

    audit = await pool.fetch("SELECT verb FROM audit_entries WHERE alert_id = $1::uuid", alert.id)
    assert [r["verb"] for r in audit] == ["alert_resolved"]
    message = await pubsub.get_message(timeout=1)
    assert message is not None and b"alert.updated" in message["data"]
    assert await redis.zcard("silence-deadlines") == 0
    await pubsub.aclose()


async def test_unflushed_folds_keep_a_silent_alert_open(pool: asyncpg.Pool, redis: Redis) -> None:
    now = datetime.now(UTC)
    alert = await insert_alert(pool, now - timedelta(minutes=10))  # Postgres says: quiet
    await redis.set(dedup_count_key("r1", "fp1"), 3)  # but 3 folds are not flushed yet
    await push_silence_deadlines(redis, [(alert.id, to_ms(now) - 1)])

    assert (
        await resolve_silent_alerts(pool, redis, {"r1": make_rule(after_silence="5m")}, to_ms(now))
        == []
    )

    assert await pool.fetchval("SELECT status FROM alerts WHERE id = $1::uuid", alert.id) == "open"
    assert await redis.zscore("silence-deadlines", alert.id) >= to_ms(now) + 300_000


async def test_failed_silence_pass_leaves_the_id_leased(
    pool: asyncpg.Pool, redis: Redis, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime.now(UTC)
    alert = await insert_alert(pool, now - timedelta(minutes=10))
    await push_silence_deadlines(redis, [(alert.id, to_ms(now) - 1)])

    async def broken_resolve(*_: object) -> None:
        raise ConnectionError("postgres down")

    monkeypatch.setattr("alerting_core.auto_resolve._resolve_and_publish", broken_resolve)
    rules = {"r1": make_rule(after_silence="5m")}

    assert await resolve_silent_alerts(pool, redis, rules, to_ms(now)) == []
    assert await redis.zscore("silence-deadlines", alert.id) == to_ms(now) + CLAIM_LEASE_MS

    monkeypatch.undo()
    later = to_ms(now) + CLAIM_LEASE_MS + 1
    assert [a.id for a in await resolve_silent_alerts(pool, redis, rules, later)] == [alert.id]
