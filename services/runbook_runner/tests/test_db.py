"""SQL, advisory lock and the full job path against Postgres (private test database)."""

import asyncio
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any

import asyncpg
import orjson
import pytest
from alerting_contracts.alerts import Alert, DeliveryJob, DeliveryPurpose, RunbookJob
from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import ActionRunStatus, Runbook
from alerting_core.config.loader import load_config_directory
from alerting_core.runbooks.store import load_runbook_file
from alerting_core.settings import Settings
from alerting_core.storage.alerts_write import insert_alerts
from alerting_core.streams import StreamMessage

from services.runbook_runner import store as store_module
from services.runbook_runner.runner import RunbookNotLoadedError, RunbookRunner
from services.runbook_runner.store import PgStore, lock_alert

from .conftest import ROOT
from .fakes import ALERT_ID, ScriptedPlugin, make_alert


class FakeRegistry:
    def __init__(self) -> None:
        result = load_config_directory(ROOT / "config")
        self.documents: dict[str, dict[str, Any]] = {}
        for document in result.documents:
            self.documents.setdefault(document.kind, {})[document.id] = document.model
        runbook = load_runbook_file(ROOT / "config/runbooks/workflow-failed.yaml")
        self.documents.setdefault("runbook", {})[runbook.id] = runbook

    def get(self, kind: str, document_id: str) -> Any:
        return self.documents.get(kind, {}).get(document_id)

    def _of(self, kind: str) -> Any:
        return MappingProxyType(self.documents.get(kind, {}))

    def actions(self) -> Any:
        return self._of("action")

    def rules(self) -> Any:
        return self._of("rule")

    def teams(self) -> Any:
        return self._of("team")

    def recipients(self) -> Any:
        return self._of("recipient")

    def channels(self) -> Any:
        return self._of("channel")


class FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, Any]]] = []

    async def publish(self, channel: str, payload: bytes) -> int:
        self.published.append((channel, orjson.loads(payload)))
        return 1


def workflow_alert() -> Alert:
    return make_alert().model_copy(
        update={
            "rule_id": "settlements-workflow-failed",
            "runbook_id": "workflow-failed",
            "last_event": {
                "workflowId": "wf-1",
                "service": "settlement-engine",
                "error": {"code": "UPSTREAM_TIMEOUT"},
            },
        }
    )


async def seed(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as connection:
        await insert_alerts(connection, [workflow_alert()])


def make_runner(pool: asyncpg.Pool, plugin: ScriptedPlugin) -> tuple[RunbookRunner, FakeRedis]:
    redis = FakeRedis()
    runner = RunbookRunner(
        pool,
        redis,  # type: ignore[arg-type]
        FakeRegistry(),  # type: ignore[arg-type]
        Settings(),
        lambda _type: plugin,
    )
    return runner, redis


def start_job() -> RunbookJob:
    return RunbookJob(job_type="start_runbook", alert_id=ALERT_ID, runbook_id="workflow-failed")


async def rows(pool: asyncpg.Pool, sql: str) -> list[asyncpg.Record]:
    return await pool.fetch(sql)


async def test_start_runbook_end_to_end_then_replay(pool: asyncpg.Pool) -> None:
    await seed(pool)
    plugin = ScriptedPlugin([True, False, False])  # health ok, retry fails twice
    runner, redis = make_runner(pool, plugin)

    assert await runner.handle_job(start_job()) == "handled"
    runs = await rows(
        pool, "SELECT step_index, status, attempt FROM action_runs ORDER BY step_index, attempt"
    )
    assert [(r["step_index"], r["status"], r["attempt"]) for r in runs] == [
        (0, "succeeded", 1),
        (1, "failed", 1),
        (1, "failed", 2),
        (2, "pending_approval", 1),
    ]
    approvals = await rows(pool, "SELECT approval_code, team, decision FROM approval_requests")
    assert len(approvals) == 1 and approvals[0]["decision"] is None
    assert approvals[0]["approval_code"].strip().isdigit()
    deliveries = [
        DeliveryJob.model_validate(r["payload"])
        for r in await rows(pool, "SELECT payload FROM outbox WHERE kind = 'delivery'")
    ]
    assert deliveries and all(d.purpose is DeliveryPurpose.approval_request for d in deliveries)
    assert {d.recipient_id for d in deliveries} == {"piotr"}
    assert all(d.content.approval_code == approvals[0]["approval_code"].strip() for d in deliveries)
    types = {payload["type"] for _, payload in redis.published}
    assert {"action_run.updated", "approval.requested", "audit.appended"} <= types
    assert {channel for channel, _ in redis.published} == {"alerts.team.settlements"}

    calls, outbox = len(plugin.calls), await pool.fetchval("SELECT count(*) FROM outbox")
    await runner.handle_job(start_job())  # replay
    assert len(plugin.calls) == calls
    assert await pool.fetchval("SELECT count(*) FROM approval_requests") == 1
    assert await pool.fetchval("SELECT count(*) FROM outbox") == outbox
    assert (
        await pool.fetchval("SELECT count(*) FROM audit_entries WHERE verb = 'runbook_started'")
        == 1
    )


async def test_execute_action_run_only_when_approved_and_continues(pool: asyncpg.Pool) -> None:
    await seed(pool)
    plugin = ScriptedPlugin([False])  # health fails -> retry skipped -> escalate pending
    runner, _ = make_runner(pool, plugin)
    await runner.handle_job(start_job())
    run_id = str(await pool.fetchval("SELECT id FROM action_runs WHERE step_index = 2"))
    job = RunbookJob(
        job_type="execute_action_run",
        alert_id=ALERT_ID,
        runbook_id="workflow-failed",
        action_run_id=run_id,
    )

    assert await runner.handle_job(job) == "skipped"  # still pending_approval
    assert len(plugin.calls) == 1

    await pool.execute("UPDATE action_runs SET status = 'approved' WHERE id = $1::uuid", run_id)
    plugin.script.append(True)
    assert await runner.handle_job(job) == "handled"
    status = await pool.fetchval("SELECT status FROM action_runs WHERE id = $1::uuid", run_id)
    assert status == "succeeded"
    assert await runner.handle_job(job) == "skipped"  # replay is a no-op
    assert len(plugin.calls) == 2


async def test_missing_alert_and_runbook_are_skipped(pool: asyncpg.Pool) -> None:
    runner, _ = make_runner(pool, ScriptedPlugin([]))
    assert await runner.handle_job(start_job()) == "skipped"
    await seed(pool)
    other = RunbookJob(job_type="start_runbook", alert_id=ALERT_ID, runbook_id="nope")
    with pytest.raises(RunbookNotLoadedError):
        await runner.handle_job(other)
    assert await pool.fetchval("SELECT count(*) FROM audit_entries") == 0


async def test_handle_batch_acks_garbage_and_fails_infrastructure_errors(
    pool: asyncpg.Pool,
) -> None:
    await seed(pool)
    runner, _ = make_runner(pool, ScriptedPlugin([True, True, True]))
    good = StreamMessage("1-0", {b"job": start_job().model_dump_json().encode()})
    garbage = StreamMessage("2-0", {b"job": b"{not json"})
    wrong = StreamMessage("3-0", {b"other": b"x"})
    dead: list[tuple[str, str]] = []

    async def dead_letter(batch: list[StreamMessage], error: str) -> None:
        dead.extend((m.id, error) for m in batch)

    runner.dead_letter = dead_letter
    assert await runner.handle_batch([good, garbage, wrong]) == {}
    assert [entry_id for entry_id, _ in dead] == ["2-0", "3-0"]

    async def boom(*_: Any, **__: Any) -> Any:
        raise ConnectionError("db down")

    runner.handle_job = boom  # type: ignore[method-assign]
    failures = await runner.handle_batch([good])
    assert list(failures) == ["1-0"] and "db down" in failures["1-0"]


async def test_advisory_lock_serializes_per_alert(pool: asyncpg.Pool) -> None:
    order: list[str] = []
    other_alert = "0197c9a0-0000-7000-8000-000000000002"

    async def worker(name: str, alert_id: str, hold: float) -> None:
        async with pool.acquire() as connection, connection.transaction():
            await lock_alert(connection, alert_id)
            order.append(f"{name}-in")
            await asyncio.sleep(hold)
            order.append(f"{name}-out")

    first = asyncio.create_task(worker("a", ALERT_ID, 0.3))
    await asyncio.sleep(0.05)
    await asyncio.gather(worker("b", ALERT_ID, 0), worker("c", other_alert, 0))
    await first
    assert order.index("a-out") < order.index("b-in")  # same alert waits
    assert order.index("c-in") < order.index("a-out")  # another alert does not


async def test_approval_code_collision_retries_in_savepoint(
    pool: asyncpg.Pool, monkeypatch: Any
) -> None:
    await seed(pool)
    codes = iter(["1111", "1111", "1111", "2222"])
    monkeypatch.setattr(store_module, "random_code", lambda: next(codes))
    async with pool.acquire() as connection, connection.transaction():
        store = PgStore(connection)
        first = await store.create_run(
            ALERT_ID, "workflow-failed", 2, "escalate", {}, ActionRunStatus.pending_approval
        )
        second = await store.create_run(
            ALERT_ID, "workflow-failed", 3, "escalate", {}, ActionRunStatus.pending_approval
        )
        one = await store.create_approval(first, "settlements", "a")
        two = await store.create_approval(second, "settlements", "b")  # 1111 x2 collide, then 2222
        assert (one.approval_code, two.approval_code) == ("1111", "2222")
        assert one.requested_at.tzinfo is not None and one.requested_at <= datetime.now(UTC)


async def test_plugin_registry_and_action_configs_exist() -> None:
    registry = FakeRegistry()
    assert isinstance(registry.get("runbook", "workflow-failed"), Runbook)
    assert isinstance(registry.actions()["escalate"], ActionConfig)


async def test_runbook_not_loaded_fails_the_entry_for_retry(pool: asyncpg.Pool) -> None:
    await seed(pool)
    runner, _ = make_runner(pool, ScriptedPlugin([True]))
    job = RunbookJob(job_type="start_runbook", alert_id=ALERT_ID, runbook_id="late")
    message = StreamMessage("9-0", {b"job": job.model_dump_json().encode()})
    failures = await runner.handle_batch([message])
    assert list(failures) == ["9-0"] and "RunbookNotLoadedError" in failures["9-0"]

    # The runbook appears (config reload): the redelivered entry now succeeds.
    registry: Any = runner._registry
    registry.documents["runbook"]["late"] = registry.documents["runbook"]["workflow-failed"]
    assert await runner.handle_batch([message]) == {}
    assert await pool.fetchval("SELECT count(*) FROM action_runs") > 0


async def test_replay_of_execute_after_reject_does_not_execute(pool: asyncpg.Pool) -> None:
    await seed(pool)
    plugin = ScriptedPlugin([False])
    runner, _ = make_runner(pool, plugin)
    await runner.handle_job(start_job())
    run_id = str(await pool.fetchval("SELECT id FROM action_runs WHERE step_index = 2"))
    job = RunbookJob(
        job_type="execute_action_run",
        alert_id=ALERT_ID,
        runbook_id="workflow-failed",
        action_run_id=run_id,
    )
    await pool.execute("UPDATE action_runs SET status = 'approved' WHERE id = $1::uuid", run_id)
    await pool.execute("UPDATE action_runs SET status = 'rejected' WHERE id = $1::uuid", run_id)
    assert await runner.handle_job(job) == "skipped"
    assert len(plugin.calls) == 1
    registry: Any = runner._registry
    registry.documents["runbook"]["other"] = registry.documents["runbook"]["workflow-failed"]
    wrong = job.model_copy(update={"runbook_id": "other"})
    assert await runner.handle_job(wrong) == "skipped"


async def test_approved_run_whose_step_vanished_is_failed(pool: asyncpg.Pool) -> None:
    await seed(pool)
    runner, _ = make_runner(pool, ScriptedPlugin([False]))
    await runner.handle_job(start_job())
    run_id = str(await pool.fetchval("SELECT id FROM action_runs WHERE step_index = 2"))
    await pool.execute(
        "UPDATE action_runs SET status = 'approved', step_index = 9 WHERE id = $1::uuid", run_id
    )
    job = RunbookJob(
        job_type="execute_action_run",
        alert_id=ALERT_ID,
        runbook_id="workflow-failed",
        action_run_id=run_id,
    )
    await runner.handle_job(job)
    row = await pool.fetchrow("SELECT status, error FROM action_runs WHERE id = $1::uuid", run_id)
    assert row["status"] == "failed" and "no longer exists" in row["error"]
    assert (
        await pool.fetchval("SELECT count(*) FROM audit_entries WHERE verb = 'action_run_failed'")
        >= 2
    )
