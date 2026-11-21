"""Phone-simulator replies: parsing, team check and reuse of the decision function."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from alerting_contracts.api import PhoneReplyResult
from alerting_contracts.runbooks import ApprovalDecision, ApprovalRequest, ApprovalVia
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.dependencies import get_pool, get_redis, get_registry
from services.api.main import create_app
from services.api.routers import phone_simulator as phone_router
from services.api.routers.approvals import AlertResolvedError, AlreadyDecidedError
from services.api.tests.test_approvals import APPROVAL_ID, make_approval

from .test_alerts import make_alert, make_audit


class FakePool:
    @asynccontextmanager
    async def acquire(self):
        yield object()


class State:
    def __init__(self) -> None:
        self.pending: ApprovalRequest | None = make_approval()
        self.channel: str | None = None
        self.decisions: list[tuple[Any, ...]] = []
        self.decide_error: Exception | None = None
        self.open_alert: str | None = None
        self.acked: list[str] = []
        self.published: int = 0


@pytest.fixture
def state(monkeypatch: pytest.MonkeyPatch) -> State:
    s = State()
    store = phone_router.store

    async def find(connection: Any, code: str) -> ApprovalRequest | None:
        return s.pending if s.pending and s.pending.approval_code == code else None

    async def channel(connection: Any, recipient_id: str, code: str) -> str | None:
        return s.channel

    async def open_alert(connection: Any, recipient_id: str) -> str | None:
        return s.open_alert

    async def decide(pool, redis, approval_id, decision, actor, via, comment=None):
        if s.decide_error:
            raise s.decide_error
        s.decisions.append((approval_id, decision, actor.id, via))

    async def ack(connection: Any, alert_id: str, actor: Any):
        s.acked.append(alert_id)
        return make_alert("acknowledged"), make_audit()

    async def publish(redis: Any, alert: Any, entries: Any) -> None:
        s.published += 1

    monkeypatch.setattr(store, "find_pending_by_code", find)
    monkeypatch.setattr(store, "latest_channel_for_code", channel)
    monkeypatch.setattr(store, "latest_open_alert_id", open_alert)
    monkeypatch.setattr(phone_router, "decide_approval", decide)
    monkeypatch.setattr(phone_router, "acknowledge_alert", ack)
    monkeypatch.setattr(phone_router, "publish_alert_change", publish)
    return s


@pytest.fixture
def client(state: State) -> TestClient:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    # Same shape as ConfigRegistry: typed accessors are methods returning mappings.
    recipients = {
        "anna": SimpleNamespace(teams=["settlements"]),
        "bob": SimpleNamespace(teams=["rates"]),
    }
    registry = SimpleNamespace(recipients=lambda: recipients)
    app.dependency_overrides[get_pool] = lambda: FakePool()
    app.dependency_overrides[get_redis] = lambda: object()
    app.dependency_overrides[get_registry] = lambda: registry
    with TestClient(app) as test_client:
        yield test_client


def reply(client: TestClient, recipient: str, text: str) -> PhoneReplyResult:
    response = client.post(
        "/api/v1/phone-simulator/replies", json={"recipient_id": recipient, "text": text}
    )
    assert response.status_code == 200
    return PhoneReplyResult.model_validate(response.json())


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("APPROVE 1234", ("approve", "1234")),
        ("approve 1234", ("approve", "1234")),
        ("  Reject    0042  ", ("reject", "0042")),
        ("\tREJECT\n9999", ("reject", "9999")),
        ("ACK", ("ack", None)),
        ("  ack ", ("ack", None)),
        ("hello", None),
        ("APPROVE", None),
        ("APPROVE 12", None),
        ("APPROVE 12345", None),
        ("APPROVE 1234 please", None),
        ("ACK 1234", None),
        ("approve abcd", None),
    ],
)
def test_parse_reply(text: str, expected: Any) -> None:
    assert phone_router.parse_reply(text) == expected


def test_garbage_lists_accepted_commands(client: TestClient, state: State) -> None:
    result = reply(client, "anna", "hello")
    assert not result.is_understood and "APPROVE" in result.message and "ACK" in result.message
    assert state.decisions == [] and state.acked == []


def test_approve_uses_decision_function_with_sms_default(client: TestClient, state: State) -> None:
    result = reply(client, "anna", "  approve   1234 ")
    assert result.is_understood and result.approval_request_id == APPROVAL_ID
    assert state.decisions == [(APPROVAL_ID, ApprovalDecision.approve, "anna", ApprovalVia.sms)]


def test_via_phone_when_latest_message_was_a_call(client: TestClient, state: State) -> None:
    state.channel = "phone"
    reply(client, "anna", "REJECT 1234")
    assert state.decisions == [(APPROVAL_ID, ApprovalDecision.reject, "anna", ApprovalVia.phone)]


def test_other_teams_code_is_not_understood_and_changes_nothing(
    client: TestClient, state: State
) -> None:
    result = reply(client, "bob", "APPROVE 1234")
    assert not result.is_understood and "1234" in result.message
    assert state.decisions == []


def test_unknown_code_and_unknown_recipient(client: TestClient, state: State) -> None:
    assert not reply(client, "anna", "APPROVE 0000").is_understood
    assert not reply(client, "ghost", "APPROVE 1234").is_understood
    assert state.decisions == []


def test_lost_race_reports_already_decided(client: TestClient, state: State) -> None:
    state.decide_error = AlreadyDecidedError(APPROVAL_ID)
    result = reply(client, "anna", "APPROVE 1234")
    assert not result.is_understood and "already decided" in result.message


def test_ack_acknowledges_latest_open_alert(client: TestClient, state: State) -> None:
    state.open_alert = "0190a0a0-0000-7000-8000-000000000001"
    result = reply(client, "anna", "ack")
    assert result.is_understood and state.acked == [state.open_alert] and state.published == 1


def test_ack_without_open_alert(client: TestClient, state: State) -> None:
    result = reply(client, "anna", "ACK")
    assert not result.is_understood and state.acked == [] and state.published == 0


def test_approve_on_resolved_alert_replies_already_resolved(
    client: TestClient, state: State
) -> None:
    state.decide_error = AlertResolvedError("x")
    result = reply(client, "anna", "APPROVE 1234")
    assert not result.is_understood and result.message == "Alert already resolved"
