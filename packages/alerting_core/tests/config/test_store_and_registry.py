import asyncio
import os
import time
from pathlib import Path

import asyncpg
import pytest
from alerting_contracts.common import Actor
from alerting_contracts.config import Team
from alerting_contracts.sse import ConfigChangedEvent
from alerting_core.config import (
    ConfigRegistry,
    handle_config_file_change,
    save_config_document,
    sync_config_files,
    watch_config_directory,
)
from pydantic import ValidationError
from redis.asyncio import Redis

pytestmark = pytest.mark.integration

ACTOR = Actor(id="anna")
CONFIG_DIR = Path(__file__).resolve().parents[4] / "config"


def _write_team(root: Path, name: str = "ops", display: str = "Ops") -> Path:
    (root / "teams").mkdir(exist_ok=True)
    file = root / "teams" / f"{name}.yaml"
    file.write_text(f"id: {name}\ndisplay_name: {display}\n")
    return file


async def test_save_bumps_version_and_publishes(pool: asyncpg.Pool, redis: Redis) -> None:
    pubsub = redis.pubsub()
    await pubsub.subscribe("config.changed", "broadcast")
    team = Team(id="ops", display_name="Ops")
    assert await save_config_document(pool, redis, "team", team, ACTOR) == 1
    updated = {"id": "ops", "display_name": "O2"}
    assert await save_config_document(pool, redis, "team", updated, ACTOR) == 2
    row = await pool.fetchrow("SELECT * FROM config_documents WHERE id = 'ops'")
    assert row["version"] == 2 and row["document"]["display_name"] == "O2"
    assert "display_name: O2" in row["yaml"] and row["updated_by"]["id"] == "anna"
    seen: set[str] = set()
    deadline = time.monotonic() + 2
    while len(seen) < 2 and time.monotonic() < deadline:
        message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2)
        if message:
            event = ConfigChangedEvent.model_validate_json(message["data"])
            assert (event.kind, event.id) == ("team", "ops")
            seen.add(message["channel"].decode())
    assert seen == {"config.changed", "broadcast"}
    await pubsub.aclose()


async def test_save_rejects_invalid_document(pool: asyncpg.Pool, redis: Redis) -> None:
    with pytest.raises(ValidationError):
        await save_config_document(pool, redis, "team", {"id": "x"}, ACTOR)
    assert await pool.fetchval("SELECT count(*) FROM config_documents") == 0


async def test_startup_inserts_new_files_and_is_idempotent(
    pool: asyncpg.Pool, redis: Redis, tmp_path: Path
) -> None:
    _write_team(tmp_path)
    await sync_config_files(pool, redis, tmp_path)
    await sync_config_files(pool, redis, tmp_path)
    assert await pool.fetchval("SELECT version FROM config_documents WHERE id = 'ops'") == 1


async def test_startup_file_newer_than_db_wins(
    pool: asyncpg.Pool, redis: Redis, tmp_path: Path
) -> None:
    await save_config_document(pool, redis, "team", Team(id="ops", display_name="Old"), ACTOR)
    file = _write_team(tmp_path, display="FromFile")
    future = time.time() + 60
    os.utime(file, (future, future))
    await sync_config_files(pool, redis, tmp_path)
    row = await pool.fetchrow("SELECT document, version FROM config_documents WHERE id = 'ops'")
    assert row["document"]["display_name"] == "FromFile" and row["version"] == 2


async def test_startup_db_newer_than_file_wins(
    pool: asyncpg.Pool, redis: Redis, tmp_path: Path
) -> None:
    file = _write_team(tmp_path, display="FromFile")
    past = time.time() - 3600
    os.utime(file, (past, past))
    await save_config_document(pool, redis, "team", Team(id="ops", display_name="FromUi"), ACTOR)
    await sync_config_files(pool, redis, tmp_path)
    row = await pool.fetchrow("SELECT document, version FROM config_documents WHERE id = 'ops'")
    assert row["document"]["display_name"] == "FromUi" and row["version"] == 1


async def test_registry_reloads_on_pubsub_within_one_second(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    registry = ConfigRegistry()
    reloads: list[int] = []
    registry.on_reload.append(lambda snapshot: reloads.append(len(snapshot.of_kind("team"))))
    await registry.start(pool, redis)
    try:
        assert registry.teams() == {}
        await save_config_document(pool, redis, "team", Team(id="ops", display_name="Ops"), ACTOR)
        deadline = time.monotonic() + 1
        while "ops" not in registry.teams() and time.monotonic() < deadline:  # noqa: ASYNC110
            await asyncio.sleep(0.02)
        assert registry.get("team", "ops").display_name == "Ops"
        assert registry.snapshot.versions[("team", "ops")] == 1
        assert reloads[-1] == 1
    finally:
        await registry.stop()


async def test_bad_row_keeps_previous_model_and_rest_still_swaps(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    registry = ConfigRegistry()
    await save_config_document(pool, redis, "team", Team(id="ops", display_name="Ops"), ACTOR)
    await registry.start(pool, redis)
    try:
        await pool.execute(
            "UPDATE config_documents SET document = '{}'::jsonb, version = 9 WHERE id = 'ops'"
        )
        await pool.execute(
            "INSERT INTO config_documents (kind, id, document, yaml)"
            " VALUES ('team', 'bad', '{}', ''),"
            " ('team', 'good', '{\"id\": \"good\", \"display_name\": \"G\"}', '')"
        )
        assert await registry.reload() is True
        assert registry.teams()["ops"].display_name == "Ops"  # previous model kept
        assert registry.snapshot.versions[("team", "ops")] == 1
        assert "bad" not in registry.teams()  # new invalid id dropped
        assert "good" in registry.teams()
    finally:
        await registry.stop()


async def test_failed_fetch_keeps_previous_snapshot(pool: asyncpg.Pool, redis: Redis) -> None:
    registry = ConfigRegistry()
    await save_config_document(pool, redis, "team", Team(id="ops", display_name="Ops"), ACTOR)
    await registry.start(pool, redis)
    try:
        before = registry.snapshot
        await pool.close()  # asyncpg.InterfaceError on the next fetch
        assert await registry.reload() is False
        assert registry.snapshot is before
    finally:
        await registry.stop()


async def test_concurrent_reloads_coalesce(pool: asyncpg.Pool, redis: Redis) -> None:
    registry = ConfigRegistry()
    await registry.start(pool, redis)
    try:
        calls: list[int] = []
        registry.on_reload.append(lambda snapshot: calls.append(1))
        await asyncio.gather(*(registry.reload() for _ in range(20)))
        assert 1 <= len(calls) <= 2
    finally:
        await registry.stop()


async def test_reconcile_reloads_when_notification_was_lost(
    pool: asyncpg.Pool, redis: Redis
) -> None:
    registry = ConfigRegistry(reconcile_interval=0.1)
    await registry.start(pool, redis)
    try:
        await pool.execute(
            "INSERT INTO config_documents (kind, id, document, yaml)"
            " VALUES ('team', 'quiet', '{\"id\": \"quiet\", \"display_name\": \"Q\"}', '')"
        )  # no publish
        deadline = time.monotonic() + 2
        while "quiet" not in registry.teams() and time.monotonic() < deadline:  # noqa: ASYNC110
            await asyncio.sleep(0.05)
        assert "quiet" in registry.teams()
    finally:
        await registry.stop()


async def test_save_rejects_model_of_wrong_kind(pool: asyncpg.Pool, redis: Redis) -> None:
    with pytest.raises(ValueError):
        await save_config_document(pool, redis, "rule", Team(id="ops", display_name="Ops"), ACTOR)
    assert await pool.fetchval("SELECT count(*) FROM config_documents") == 0


async def test_concurrent_startup_syncs_write_once(
    pool: asyncpg.Pool, redis: Redis, tmp_path: Path
) -> None:
    _write_team(tmp_path)
    await asyncio.gather(*(sync_config_files(pool, redis, tmp_path) for _ in range(5)))
    assert await pool.fetchval("SELECT version FROM config_documents WHERE id = 'ops'") == 1


async def test_watcher_handler_saves_valid_and_skips_invalid(
    pool: asyncpg.Pool, redis: Redis, tmp_path: Path
) -> None:
    file = _write_team(tmp_path)
    assert await handle_config_file_change(file, pool, redis) is True
    assert await handle_config_file_change(file, pool, redis) is False  # unchanged content
    row = await pool.fetchrow("SELECT version, updated_by FROM config_documents WHERE id = 'ops'")
    assert row["version"] == 1 and row["updated_by"]["id"] == "system:config-watcher"
    file.write_text("id: ops\n")  # missing display_name
    assert await handle_config_file_change(file, pool, redis) is False
    assert await pool.fetchval("SELECT version FROM config_documents WHERE id = 'ops'") == 1


@pytest.mark.slow
async def test_real_file_watcher_picks_up_an_edit(
    pool: asyncpg.Pool, redis: Redis, tmp_path: Path
) -> None:
    _write_team(tmp_path)
    task = asyncio.create_task(watch_config_directory(tmp_path, pool, redis))
    try:
        await asyncio.sleep(1.5)
        _write_team(tmp_path, display="Edited")
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            doc = await pool.fetchval("SELECT document FROM config_documents WHERE id = 'ops'")
            if doc and doc["display_name"] == "Edited":
                return
            await asyncio.sleep(0.1)
        pytest.fail("watcher did not save the edit")
    finally:
        task.cancel()


async def test_schema_profile_kind_matches_contract(pool: asyncpg.Pool, redis: Redis) -> None:
    from alerting_core.config import load_config_directory

    profile = next(
        d for d in load_config_directory(CONFIG_DIR).documents if d.file.parent.name == "schemas"
    )
    assert profile.kind == "schema_profile"
    await save_config_document(pool, redis, "schema_profile", profile.model, ACTOR)
    registry = ConfigRegistry()
    await registry.start(pool, redis)
    try:
        assert profile.id in registry.schema_profiles()
    finally:
        await registry.stop()


async def test_start_failure_leaves_no_tasks(pool: asyncpg.Pool) -> None:
    unreachable = Redis.from_url("redis://localhost:1/12")
    registry = ConfigRegistry(initial_load_timeout=1.0)
    with pytest.raises(Exception):  # noqa: B017 - timeout or connection error, both acceptable
        await registry.start(pool, unreachable)
    assert registry._tasks == []
    await unreachable.aclose()


async def test_sync_loads_files_off_the_event_loop_with_llm_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import threading

    from alerting_core.config import store as config_store
    from alerting_core.config.loader import LoadResult

    seen: dict[str, object] = {}

    def fake_load(path: Path | str) -> LoadResult:
        seen["thread"] = threading.current_thread()
        seen["llm"] = config_store.NORMALIZE_TEXT_WITH_LLM.get()
        return LoadResult()

    monkeypatch.setattr(config_store, "load_config_directory", fake_load)
    await sync_config_files(None, None, tmp_path)  # type: ignore[arg-type]
    assert seen["thread"] is not threading.main_thread() and seen["llm"] is True
    assert config_store.NORMALIZE_TEXT_WITH_LLM.get() is False  # caller context untouched
