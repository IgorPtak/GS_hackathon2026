"""Alerts routes with storage functions and Redis faked (no database)."""

from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest
from alerting_contracts.alerts import Alert, AlertStatus, AuditEntry, AuditVerb
from alerting_contracts.api import AlertDetail, AlertPage, ErrorResponse
from alerting_contracts.common import Actor
from alerting_core.settings import Settings
from alerting_core.storage import AlertNotFoundError, InvalidCursorError, InvalidTransitionError
from fastapi.testclient import TestClient

from services.api.dependencies import get_pool, get_redis
from services.api.main import create_app
from services.api.routers import alerts as alerts_router
from services.api.routers.runbooks import get_catalog

ALERT_ID = "0190a0a0-0000-7000-8000-000000000001"
ACTOR = {"id": "anna"}


def make_alert(status: str = "open") -> Alert:
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
        status=status,
        first_seen=now,
        last_seen=now,
        last_event={},
        updated_at=now,
    )


def make_audit() -> AuditEntry:
    return AuditEntry(
        id=1,
        alert_id=ALERT_ID,
        at=datetime.now(UTC),
        actor=Actor(id="anna"),
        verb=AuditVerb.alert_acknowledged,
    )


class FakePool:
    @asynccontextmanager
    async def acquire(self):
        yield object()


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    calls: list[Any] = []

    async def fake_publish(redis: Any, alert: Alert, entries: list[AuditEntry]) -> None:
        calls.append((alert, entries))

    monkeypatch.setattr(alerts_router, "publish_alert_change", fake_publish)
    return calls


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    app.dependency_overrides[get_pool] = lambda: FakePool()
    app.dependency_overrides[get_redis] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client


def fake(value: Any = None, error: Exception | None = None) -> Callable[..., Any]:
    async def call(*args: Any, **kwargs: Any) -> Any:
        if error:
            raise error
        return value

    return call


def test_list_passes_filters_and_returns_page(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    async def fake_list(pool: Any, team: str, status: Any, limit: int, cursor: Any) -> AlertPage:
        seen.update(team=team, status=status, limit=limit, cursor=cursor)
        return AlertPage(items=[make_alert()], next_cursor="n")

    monkeypatch.setattr(alerts_router, "list_alerts", fake_list)
    body = client.get("/api/v1/alerts?team=rates&status=open&limit=5&cursor=c").json()
    assert seen == {"team": "rates", "status": [AlertStatus.open], "limit": 5, "cursor": "c"}
    assert body["next_cursor"] == "n" and body["items"][0]["id"] == ALERT_ID


def test_list_bad_cursor_is_400(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alerts_router, "list_alerts", fake(error=InvalidCursorError("invalid")))
    response = client.get("/api/v1/alerts?team=rates&cursor=zzz")
    assert response.status_code == 400
    assert ErrorResponse.model_validate(response.json()).error == "bad_request"


def test_list_limit_over_200_is_422(client: TestClient) -> None:
    assert client.get("/api/v1/alerts?team=rates&limit=201").status_code == 422


def test_detail_ok_and_runbook_none(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    detail = AlertDetail(alert=make_alert(), audit_entries=[], deliveries=[])
    monkeypatch.setattr(alerts_router, "get_alert_detail", fake(detail))
    body = client.get(f"/api/v1/alerts/{ALERT_ID}").json()
    assert body["alert"]["id"] == ALERT_ID and body["rendered_runbook"] is None


def test_detail_404(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alerts_router, "get_alert_detail", fake(error=AlertNotFoundError("x")))
    response = client.get(f"/api/v1/alerts/{ALERT_ID}")
    assert response.status_code == 404
    assert ErrorResponse.model_validate(response.json()).error == "not_found"


def test_acknowledge_publishes_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, published: list[Any]
) -> None:
    monkeypatch.setattr(
        alerts_router, "acknowledge_alert", fake((make_alert("acknowledged"), make_audit()))
    )
    response = client.post(f"/api/v1/alerts/{ALERT_ID}/acknowledge", json={"actor": ACTOR})
    assert response.status_code == 200 and response.json()["status"] == "acknowledged"
    assert len(published) == 1 and len(published[0][1]) == 1


def test_resolve_passes_comment_and_publishes_once(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, published: list[Any]
) -> None:
    seen: dict[str, Any] = {}

    async def fake_resolve(conn: Any, alert_id: str, actor: Actor, reason: Any, comment: Any):
        seen.update(alert_id=alert_id, comment=comment, reason=reason.value)
        return make_alert("resolved"), make_audit()

    monkeypatch.setattr(alerts_router, "resolve_alert", fake_resolve)
    response = client.post(
        f"/api/v1/alerts/{ALERT_ID}/resolve", json={"actor": ACTOR, "comment": "fixed"}
    )
    assert response.status_code == 200
    assert seen == {"alert_id": ALERT_ID, "comment": "fixed", "reason": "manual"}
    assert len(published) == 1


@pytest.mark.parametrize(
    ("verb", "name", "status", "code", "error"),
    [
        (
            "acknowledge",
            "acknowledge_alert",
            409,
            "invalid_transition",
            InvalidTransitionError("no"),
        ),
        ("resolve", "resolve_alert", 409, "invalid_transition", InvalidTransitionError("no")),
        ("acknowledge", "acknowledge_alert", 404, "not_found", AlertNotFoundError("x")),
        ("resolve", "resolve_alert", 404, "not_found", AlertNotFoundError("x")),
    ],
)
def test_transition_errors_are_error_responses_and_do_not_publish(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    published: list[Any],
    verb: str,
    name: str,
    status: int,
    code: str,
    error: Exception,
) -> None:
    monkeypatch.setattr(alerts_router, name, fake(error=error))
    response = client.post(f"/api/v1/alerts/{ALERT_ID}/{verb}", json={"actor": ACTOR})
    assert response.status_code == status
    assert ErrorResponse.model_validate(response.json()).error == code
    assert published == []


def test_missing_actor_is_422(client: TestClient) -> None:
    assert client.post(f"/api/v1/alerts/{ALERT_ID}/acknowledge", json={}).status_code == 422


class StubCatalog:
    def __init__(self, runbook: Any = None, error: Exception | None = None) -> None:
        self._runbook, self._error = runbook, error

    def get(self, runbook_id: str) -> Any:
        if self._error:
            raise self._error
        return self._runbook

    def actions(self) -> dict[str, Any]:
        return {}


def detail_with_runbook() -> AlertDetail:
    alert = make_alert().model_copy(
        update={"runbook_id": "workflow-failed", "last_event": {"workflowId": "wf-1"}}
    )
    return AlertDetail(alert=alert, audit_entries=[], deliveries=[])


def test_detail_renders_runbook(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from alerting_contracts.runbooks import Runbook, RunbookFormat, RunbookStep, StepKind

    runbook = Runbook(
        id="workflow-failed",
        title="WF",
        format=RunbookFormat.text,
        source="s",
        steps=[RunbookStep(index=0, kind=StepKind.text, text="Check {{ workflowId }}")],
        normalized_by="parser",
    )
    monkeypatch.setattr(alerts_router, "get_alert_detail", fake(detail_with_runbook()))
    client.app.dependency_overrides[get_catalog] = lambda: StubCatalog(runbook)
    body = client.get(f"/api/v1/alerts/{ALERT_ID}").json()
    assert body["rendered_runbook"]["runbook_id"] == "workflow-failed"
    assert "wf-1" in body["rendered_runbook"]["steps"][0]["text"]


def test_detail_missing_runbook_is_none(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(alerts_router, "get_alert_detail", fake(detail_with_runbook()))
    client.app.dependency_overrides[get_catalog] = lambda: StubCatalog(None)
    assert client.get(f"/api/v1/alerts/{ALERT_ID}").json()["rendered_runbook"] is None


def test_detail_render_failure_is_none(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(alerts_router, "get_alert_detail", fake(detail_with_runbook()))
    client.app.dependency_overrides[get_catalog] = lambda: StubCatalog(error=RuntimeError("boom"))
    response = client.get(f"/api/v1/alerts/{ALERT_ID}")
    assert response.status_code == 200 and response.json()["rendered_runbook"] is None
