"""runRunbookStep with storage, outbox, audit and publishing faked (no database)."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from unittest import mock

import pytest
from alerting_contracts.alerts import Alert, AuditEntry, AuditVerb, RunbookJob
from alerting_contracts.api import ErrorResponse
from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import ActionRun, ActionRunStatus, ApprovalRequest, Runbook
from alerting_core.settings import Settings
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

from services.api.dependencies import get_pool, get_redis, get_registry
from services.api.main import create_app
from services.api.routers import runbook_runs
from services.api.routers.runbooks import get_catalog

ALERT_ID = "0190a0a0-0000-7000-8000-000000000001"
ACTOR = {"id": "anna"}
URL = f"/api/v1/alerts/{ALERT_ID}/runbook/steps/{{}}/run"


def make_runbook(approval: str | None = None) -> Runbook:
    step: dict[str, Any] = {"index": 0, "kind": "action", "text": "Restart", "action": "restart"}
    if approval:
        step["approval"] = approval
    return Runbook(
        id="rb",
        title="rb",
        format="yaml",
        source="",
        steps=[step, {"index": 1, "kind": "text", "text": "Just read"}],
        normalized_by="parser",
    )


class Catalog:
    def __init__(self, runbook: Runbook) -> None:
        self._runbook = runbook

    def get(self, runbook_id: str) -> Runbook | None:
        return self._runbook if runbook_id == "rb" else None

    def actions(self) -> dict[str, ActionConfig]:
        return {"restart": ActionConfig(id="restart", type="webhook")}


class Env:
    def __init__(self) -> None:
        self.status = "open"
        self.runbook_id: str | None = "rb"
        self.runs: list[ActionRun] = []
        self.jobs: list[RunbookJob] = []
        self.audits: list[tuple[AuditVerb, str]] = []
        self.approvals: list[ApprovalRequest] = []
        self.published: list[str] = []


class FakeConnection:
    @asynccontextmanager
    async def transaction(self):
        yield


class FakePool:
    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection()


def alert(env: Env) -> Alert:
    now = datetime.now(UTC)
    return Alert(
        id=ALERT_ID,
        rule_id="r",
        team="rates",
        schema_profile_id="p",
        source_id="s",
        fingerprint="f",
        severity="error",
        title="t",
        status=env.status,
        runbook_id=env.runbook_id,
        first_seen=now,
        last_seen=now,
        last_event={},
        updated_at=now,
    )


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Env:
    state = Env()

    async def lock(connection: Any, alert_id: str) -> str:
        return state.status

    async def fake_get_alert(connection: Any, alert_id: str) -> Alert:
        return alert(state)

    class FakeStore:
        def __init__(self, connection: Any) -> None:
            pass

        async def runs_for_step(self, alert_id: str, runbook_id: str, index: int):
            return [r for r in state.runs if r.step_index == index]

        async def create_run(
            self, alert_id, runbook_id, step_index, action_id, params, status, attempt, requested_by
        ) -> ActionRun:
            now = datetime.now(UTC)
            run = ActionRun(
                id=f"0190a0a0-0000-7000-8000-0000000000b{len(state.runs)}",
                alert_id=alert_id,
                runbook_id=runbook_id,
                step_index=step_index,
                action_id=action_id,
                params=params,
                status=status,
                attempt=attempt,
                requested_by=requested_by,
                created_at=now,
                updated_at=now,
            )
            state.runs.append(run)
            return run

        async def create_approval(self, run: ActionRun, team: str, summary: str):
            approval = ApprovalRequest(
                id="0190a0a0-0000-7000-8000-0000000000a1",
                action_run_id=run.id,
                alert_id=run.alert_id,
                team=team,
                runbook_id=run.runbook_id,
                step_index=run.step_index,
                action_id=run.action_id,
                summary=summary,
                approval_code="1234",
                requested_at=datetime.now(UTC),
            )
            state.approvals.append(approval)
            return approval

    class FakeNotifier:
        def __init__(self, connection: Any, **kwargs: Any) -> None:
            pass

        async def notify(self, alert: Alert, approval: ApprovalRequest) -> int:
            return 0

    async def enqueue(connection: Any, job: RunbookJob) -> int:
        state.jobs.append(job)
        return 1

    async def audit(connection: Any, alert_id, actor, verb, outcome="ok", detail=None):
        state.audits.append((verb, outcome))
        return AuditEntry(
            id=1, alert_id=alert_id, at=datetime.now(UTC), actor=actor, verb=verb, detail=detail
        )

    async def publish(redis: Any, team: str, event: Any) -> None:
        state.published.append(event.type)

    monkeypatch.setattr(runbook_runs.approvals_store, "lock_alert_status", lock)
    monkeypatch.setattr(runbook_runs, "get_alert", fake_get_alert)
    monkeypatch.setattr(runbook_runs, "PgStore", FakeStore)
    monkeypatch.setattr(runbook_runs, "OutboxApprovalNotifier", FakeNotifier)
    monkeypatch.setattr(runbook_runs, "enqueue_runbook_job", enqueue)
    monkeypatch.setattr(runbook_runs, "append_audit", audit)
    monkeypatch.setattr(runbook_runs, "publish_team_event", publish)
    return state


def make_client(runbook: Runbook) -> TestClient:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    app.dependency_overrides[get_pool] = lambda: FakePool()
    app.dependency_overrides[get_redis] = lambda: object()
    app.dependency_overrides[get_catalog] = lambda: Catalog(runbook)
    app.dependency_overrides[get_registry] = lambda: mock.Mock()
    return TestClient(app)


@pytest.fixture
def client(env: Env) -> TestClient:
    with make_client(make_runbook()) as test_client:
        yield test_client


def post(client: TestClient, index: int = 0):
    return client.post(URL.format(index), json={"actor": ACTOR})


def test_run_creates_run_audit_and_job(client: TestClient, env: Env) -> None:
    response = post(client)
    assert response.status_code == 202
    body = ActionRun.model_validate(response.json())
    assert body.status is ActionRunStatus.approved and body.requested_by.id == "anna"
    assert len(env.runs) == 1
    assert env.jobs == [
        RunbookJob(
            job_type="execute_action_run",
            alert_id=ALERT_ID,
            runbook_id="rb",
            action_run_id=body.id,
        )
    ]
    assert env.audits == [(AuditVerb.action_run_started, "pending")]
    assert env.published == ["action_run.updated", "audit.appended"]


def test_resolved_alert_is_409(client: TestClient, env: Env) -> None:
    env.status = "resolved"
    response = post(client)
    assert response.status_code == 409
    assert ErrorResponse.model_validate(response.json()).error == "alert_resolved"
    assert env.runs == [] and env.jobs == []


def test_second_run_is_409_but_a_failed_run_can_be_retried(client: TestClient, env: Env) -> None:
    assert post(client).status_code == 202
    assert post(client).status_code == 409
    env.runs[0] = env.runs[0].model_copy(update={"status": ActionRunStatus.failed})
    retry = post(client)
    assert retry.status_code == 202 and retry.json()["attempt"] == 2
    assert len(env.jobs) == 2


def test_step_without_action_is_422(client: TestClient, env: Env) -> None:
    response = post(client, 1)
    assert response.status_code == 422
    assert env.runs == [] and env.jobs == []


def test_unknown_step_or_alert_or_runbook_is_404(client: TestClient, env: Env) -> None:
    assert post(client, 9).status_code == 404
    env.runbook_id = None
    assert post(client).status_code == 404
    bad = client.post("/api/v1/alerts/nope/runbook/steps/0/run", json={"actor": ACTOR})
    assert bad.status_code == 404


def test_approval_required_step_creates_approval_and_no_job(env: Env) -> None:
    with make_client(make_runbook(approval="required")) as client:
        response = post(client)
    assert response.status_code == 202
    assert response.json()["status"] == "pending_approval"
    assert len(env.approvals) == 1
    assert env.jobs == []
    assert env.audits == [(AuditVerb.approval_requested, "pending")]
    assert "approval.requested" in env.published


def test_event_publish_failure_still_returns_202(
    client: TestClient, env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(redis: Any, team: str, event: Any) -> None:
        raise RedisError("down")

    monkeypatch.setattr(runbook_runs, "publish_team_event", boom)
    response = post(client)
    assert response.status_code == 202
    assert len(env.runs) == 1
