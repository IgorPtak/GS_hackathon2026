"""Approval routes with storage, outbox, audit and publishing faked (no database)."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from alerting_contracts.alerts import AuditEntry, AuditVerb, RunbookJob
from alerting_contracts.api import ErrorResponse
from alerting_contracts.runbooks import (
    ActionRun,
    ActionRunStatus,
    ApprovalDecision,
    ApprovalRequest,
)
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.dependencies import get_pool, get_redis
from services.api.main import create_app
from services.api.routers import approvals as approvals_router

APPROVAL_ID = "0190a0a0-0000-7000-8000-0000000000a1"
RUN_ID = "0190a0a0-0000-7000-8000-0000000000b1"
ALERT_ID = "0190a0a0-0000-7000-8000-000000000001"
ACTOR = {"id": "anna"}


def make_approval(decision: str | None = None) -> ApprovalRequest:
    return ApprovalRequest(
        id=APPROVAL_ID,
        action_run_id=RUN_ID,
        alert_id=ALERT_ID,
        team="settlements",
        runbook_id="workflow-failed",
        step_index=2,
        action_id="restart-workflow",
        summary="Restart",
        approval_code="1234",
        requested_at=datetime.now(UTC),
        decision=decision,
    )


class Env:
    """Records every side effect in order so tests can assert commit-before-publish."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.jobs: list[RunbookJob] = []
        self.published: list[str] = []
        self.audits: list[dict[str, Any]] = []
        self.run_statuses: list[ActionRunStatus] = []
        self.current: ApprovalRequest | None = make_approval()


class FakeConnection:
    def __init__(self, env: Env) -> None:
        self.env = env

    @asynccontextmanager
    async def transaction(self):
        self.env.events.append("begin")
        yield
        self.env.events.append("commit")


class FakePool:
    def __init__(self, env: Env) -> None:
        self.env = env

    @asynccontextmanager
    async def acquire(self):
        yield FakeConnection(self.env)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Env:
    state = Env()
    store = approvals_router.store

    async def lock(connection: Any, approval_id: str) -> ApprovalRequest | None:
        state.events.append("lock")
        return state.current

    async def record(connection: Any, approval_id, decision, actor, via, comment):
        assert state.current is not None
        return state.current.model_copy(
            update={
                "decision": decision,
                "decided_by": actor,
                "decided_via": via,
                "decided_at": datetime.now(UTC),
                "comment": comment,
            }
        )

    async def set_status(connection: Any, run_id: str, status: ActionRunStatus) -> ActionRun:
        state.run_statuses.append(status)
        now = datetime.now(UTC)
        return ActionRun(
            id=run_id,
            alert_id=ALERT_ID,
            runbook_id="workflow-failed",
            step_index=2,
            action_id="restart-workflow",
            params={},
            status=status,
            requested_by={"id": "runbook-runner"},
            created_at=now,
            updated_at=now,
        )

    async def enqueue(connection: Any, job: RunbookJob) -> int:
        state.events.append("enqueue")
        state.jobs.append(job)
        return 1

    async def audit(connection: Any, alert_id, actor, verb, outcome="ok", detail=None):
        state.events.append("audit")
        state.audits.append({"verb": verb, "detail": detail, "actor": actor})
        return AuditEntry(
            id=1,
            alert_id=alert_id,
            at=datetime.now(UTC),
            actor=actor,
            verb=verb,
            detail=detail or {},
        )

    async def publish(redis: Any, team: str, event: Any) -> None:
        state.events.append("publish")
        state.published.append(f"{team}:{event.type}")

    monkeypatch.setattr(store, "lock_approval", lock)
    monkeypatch.setattr(store, "record_decision", record)
    monkeypatch.setattr(store, "set_run_status", set_status)
    monkeypatch.setattr(approvals_router, "enqueue_runbook_job", enqueue)
    monkeypatch.setattr(approvals_router, "append_audit", audit)
    monkeypatch.setattr(approvals_router, "publish_team_event", publish)
    return state


@pytest.fixture
def client(env: Env) -> TestClient:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    app.dependency_overrides[get_pool] = lambda: FakePool(env)
    app.dependency_overrides[get_redis] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client


def decide(client: TestClient, decision: str, approval_id: str = APPROVAL_ID) -> Any:
    return client.post(
        f"/api/v1/approvals/{approval_id}/decision",
        json={"decision": decision, "actor": ACTOR, "comment": "ok"},
    )


def test_approve_enqueues_one_job_audits_and_publishes_after_commit(
    client: TestClient, env: Env
) -> None:
    response = decide(client, "approve")
    assert response.status_code == 200
    body = ApprovalRequest.model_validate(response.json())
    assert body.decision is ApprovalDecision.approve and body.decided_via == "ui"
    assert env.jobs == [
        RunbookJob(
            job_type="execute_action_run",
            alert_id=ALERT_ID,
            runbook_id="workflow-failed",
            action_run_id=RUN_ID,
        )
    ]
    assert env.run_statuses == [ActionRunStatus.approved]
    assert env.audits[0]["verb"] is AuditVerb.approval_decided
    assert env.audits[0]["detail"]["decision"] == "approve"
    assert env.audits[0]["detail"]["decided_via"] == "ui"
    assert env.audits[0]["detail"]["code"] == "1234"
    assert env.published == [
        "settlements:approval.decided",
        "settlements:action_run.updated",
        "settlements:audit.appended",
    ]
    assert env.events.index("commit") < env.events.index("publish")
    assert env.events[:2] == ["begin", "lock"]


def test_reject_enqueues_nothing(client: TestClient, env: Env) -> None:
    response = decide(client, "reject")
    assert response.status_code == 200 and response.json()["decision"] == "reject"
    assert env.jobs == [] and env.run_statuses == [ActionRunStatus.rejected]
    assert len(env.published) == 3


def test_second_decision_is_409_and_publishes_nothing(client: TestClient, env: Env) -> None:
    env.current = make_approval("approve")
    response = decide(client, "reject")
    assert response.status_code == 409
    assert ErrorResponse.model_validate(response.json()).error == "already_decided"
    assert env.jobs == [] and env.published == [] and env.audits == []
    assert "commit" not in env.events


def test_unknown_is_404(client: TestClient, env: Env) -> None:
    env.current = None
    response = decide(client, "approve")
    assert response.status_code == 404
    assert ErrorResponse.model_validate(response.json()).error == "not_found"
    assert env.published == []


def test_malformed_id_is_404_without_touching_db(client: TestClient, env: Env) -> None:
    assert decide(client, "approve", "not-a-uuid").status_code == 404
    assert env.events == []


def test_list_passes_filters(client: TestClient, env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[Any] = []

    async def fake_list(pool: Any, team: Any, is_pending: bool) -> list[ApprovalRequest]:
        seen.append((team, is_pending))
        return [make_approval()]

    monkeypatch.setattr(approvals_router.store, "list_approvals", fake_list)
    body = client.get("/api/v1/approvals?team=settlements").json()
    assert body[0]["approval_code"] == "1234" and seen == [("settlements", True)]
    client.get("/api/v1/approvals?is_pending=false")
    assert seen[-1] == (None, False)
