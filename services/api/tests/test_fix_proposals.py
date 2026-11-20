"""Fix-proposal routes with storage, audit, saves and publishing faked (no database)."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest
from alerting_contracts.alerts import Alert, AuditEntry
from alerting_contracts.api import ErrorResponse
from alerting_contracts.config import Rule
from alerting_contracts.proposals import FixProposal, ProposalStatus
from alerting_contracts.runbooks import Runbook
from alerting_core.config.store import canonical_document
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.dependencies import get_pool, get_redis, get_registry
from services.api.main import create_app
from services.api.routers import fix_proposals as fixr
from services.api.routers.runbooks import get_catalog

ALERT_ID = "0190a0a0-0000-7000-8000-000000000001"
PROPOSAL_ID = "0190a0a0-0000-7000-8000-0000000000c1"
ACTOR = {"id": "anna"}
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def rule_doc(title: str = "Rejected {{payload.currency}}", team: str = "rates") -> dict[str, Any]:
    return {
        "id": "r1",
        "team": team,
        "when": {"field": "normalized.type", "op": "glob", "value": "trade.*"},
        "present": {"title": title, "body": "b"},
    }


def step_doc(index: int, text: str = "new") -> dict[str, Any]:
    return {"index": index, "kind": "text", "text": text}


def make_runbook() -> Runbook:
    return Runbook(
        id="rb1",
        title="t",
        team="rates",
        format="yaml",
        source="s",
        steps=[step_doc(0, "a"), step_doc(1, "b"), step_doc(2, "c")],
        normalized_by="parser",
    )


def make_alert(team: str = "platform", runbook_id: str | None = "rb1") -> Alert:
    return Alert(
        id=ALERT_ID,
        rule_id="r1",
        team=team,
        schema_profile_id="p",
        source_id="s",
        fingerprint="f",
        severity="error",
        title="t",
        runbook_id=runbook_id,
        first_seen=NOW,
        last_seen=NOW,
        last_event={},
        updated_at=NOW,
    )


class Env:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.published: list[str] = []
        self.audits: list[dict[str, Any]] = []
        self.saved_rules: list[Rule] = []
        self.saved_runbooks: list[Runbook] = []
        self.alert: Alert | None = make_alert()
        self.rows: dict[str, FixProposal] = {}
        self.runbook: Runbook | None = make_runbook()
        self.fail_save = False
        self.fail_mark = False
        self.stored: dict[str, Any] | None = None
        self.rule_team: str | None = "rates"
        self.listed: list[tuple[Any, Any]] = []


class FakeConnection:
    def __init__(self, env: Env) -> None:
        self.env = env

    @asynccontextmanager
    async def transaction(self):
        self.env.events.append("begin")
        try:
            yield
        except BaseException:
            self.env.events.append("rollback")
            raise
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
    store = fixr.store

    async def get_alert(connection: Any, alert_id: str) -> Alert:
        if state.alert is None:
            raise fixr.AlertNotFoundError(alert_id)
        return state.alert

    async def insert(connection: Any, alert: Alert, owner_team: str, body: Any) -> FixProposal:
        state.events.append("insert")
        proposal = FixProposal(
            id=PROPOSAL_ID,
            alert_id=alert.id,
            rule_id=alert.rule_id,
            runbook_id=alert.runbook_id,
            owner_team=owner_team,
            kind=body.kind,
            description=body.description,
            proposed_rule=body.proposed_rule,
            proposed_runbook_step=body.proposed_runbook_step,
            proposed_by=body.proposed_by,
            created_at=NOW,
        )
        state.rows[proposal.id] = proposal
        return proposal

    async def lock(connection: Any, proposal_id: str) -> FixProposal | None:
        state.events.append("lock")
        return state.rows.get(proposal_id)

    async def mark(connection: Any, proposal_id, status, actor, comment) -> FixProposal:
        state.events.append("mark")
        if state.fail_mark:
            raise RuntimeError("crash before mark")
        updated = state.rows[proposal_id].model_copy(
            update={
                "status": status,
                "decided_by": actor,
                "decided_at": NOW,
                "decision_comment": comment,
            }
        )
        state.rows[proposal_id] = updated
        return updated

    async def list_(pool: Any, team: str | None, status: ProposalStatus | None):
        state.listed.append((team, status))
        rows = [
            p
            for p in state.rows.values()
            if (team is None or p.owner_team == team) and (status is None or p.status == status)
        ]
        return rows

    async def audit(connection: Any, alert_id, actor, verb, outcome="ok", detail=None):
        state.events.append("audit")
        state.audits.append({"verb": verb, "detail": detail})
        return AuditEntry(
            id=1, alert_id=alert_id, at=NOW, actor=actor, verb=verb, detail=detail or {}
        )

    async def save_rule(pool: Any, redis: Any, kind: str, document: Any, actor: Any) -> int:
        state.events.append("save_rule")
        if state.fail_save:
            raise RuntimeError("db down")
        state.saved_rules.append(document)
        state.stored = canonical_document(document)
        return 7

    async def get_stored(pool: Any, rule_id: str) -> Any:
        return (state.stored, 7) if state.stored is not None else None

    async def save_rb(pool: Any, redis: Any, runbook: Runbook, actor: Any) -> int:
        state.events.append("save_runbook")
        state.saved_runbooks.append(runbook)
        state.runbook = runbook.model_copy(update={"version": 3})
        return 3

    async def publish(redis: Any, team: str, event: Any) -> None:
        state.events.append("publish")
        state.published.append(f"{team}:{event.type}")

    monkeypatch.setattr(fixr, "get_alert", get_alert)
    monkeypatch.setattr(store, "insert_proposal", insert)
    monkeypatch.setattr(store, "lock_proposal", lock)
    monkeypatch.setattr(store, "mark_decided", mark)
    monkeypatch.setattr(store, "list_proposals", list_)
    monkeypatch.setattr(store, "get_rule_document", get_stored)
    monkeypatch.setattr(fixr, "append_audit", audit)
    monkeypatch.setattr(fixr, "save_config_document", save_rule)
    monkeypatch.setattr(fixr, "save_runbook", save_rb)
    monkeypatch.setattr(fixr, "publish_team_event", publish)
    return state


@pytest.fixture
def client(env: Env) -> TestClient:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    app.dependency_overrides[get_pool] = lambda: FakePool(env)
    app.dependency_overrides[get_redis] = lambda: object()

    def registry() -> Any:
        if env.rule_team is None:
            return SimpleNamespace(rules=lambda: {})
        rule = Rule.model_validate(rule_doc(team=env.rule_team))
        return SimpleNamespace(rules=lambda: {"r1": rule})

    app.dependency_overrides[get_registry] = registry
    app.dependency_overrides[get_catalog] = lambda: SimpleNamespace(get=lambda _id: env.runbook)
    with TestClient(app) as test_client:
        yield test_client


def create(client: TestClient, **fields: Any) -> Any:
    body = {"kind": "other", "description": "d", "proposed_by": ACTOR, **fields}
    return client.post(f"/api/v1/alerts/{ALERT_ID}/fix-proposals", json=body)


def decide(client: TestClient, decision: str, proposal_id: str = PROPOSAL_ID) -> Any:
    return client.post(
        f"/api/v1/fix-proposals/{proposal_id}/decision",
        json={"decision": decision, "actor": {"id": "bob"}, "comment": "why"},
    )


def paths(response: Any) -> list[str]:
    return [d.path for d in ErrorResponse.model_validate(response.json()).details]


def test_create_other_resolves_owner_team_audits_and_publishes_to_both(
    client: TestClient, env: Env
) -> None:
    response = create(client)
    assert response.status_code == 201
    body = FixProposal.model_validate(response.json())
    assert body.owner_team == "rates" and body.rule_id == "r1" and body.runbook_id == "rb1"
    assert env.audits[0]["verb"].value == "fix_proposed"
    assert env.published == [
        "rates:fix_proposal.updated",
        "rates:audit.appended",
        "platform:fix_proposal.updated",
        "platform:audit.appended",
    ]
    assert env.events.index("commit") < env.events.index("publish")
    assert env.events.index("insert") < env.events.index("audit") < env.events.index("commit")


def test_owner_team_falls_back_to_alert_team_and_publishes_once(
    client: TestClient, env: Env
) -> None:
    env.rule_team = None
    env.alert = make_alert(team="platform")
    body = FixProposal.model_validate(create(client).json())
    assert body.owner_team == "platform"
    assert env.published == ["platform:fix_proposal.updated", "platform:audit.appended"]


def test_create_unknown_alert_is_404(client: TestClient, env: Env) -> None:
    env.alert = None
    assert create(client).status_code == 404
    assert env.published == []


@pytest.mark.parametrize("kind", ["threshold", "fields", "dedup_window"])
def test_rule_kinds_need_matching_rule(client: TestClient, env: Env, kind: str) -> None:
    missing = create(client, kind=kind)
    assert missing.status_code == 422 and paths(missing) == ["proposed_rule"]
    wrong = rule_doc() | {"id": "other"}
    mismatch = create(client, kind=kind, proposed_rule=wrong)
    assert mismatch.status_code == 422 and paths(mismatch) == ["proposed_rule.id"]
    assert create(client, kind=kind, proposed_rule=rule_doc()).status_code == 201
    assert env.published and len(env.rows) == 1


def test_runbook_step_validation(client: TestClient, env: Env) -> None:
    missing = create(client, kind="runbook_step")
    assert missing.status_code == 422 and paths(missing) == ["proposed_runbook_step"]
    env.alert = make_alert(runbook_id=None)
    no_runbook = create(client, kind="runbook_step", proposed_runbook_step=step_doc(1))
    assert no_runbook.status_code == 422 and paths(no_runbook) == ["kind"]
    env.alert = make_alert()
    assert create(client, kind="runbook_step", proposed_runbook_step=step_doc(1)).status_code == 201


def test_other_rejects_payload_and_bad_body_has_dot_path(client: TestClient, env: Env) -> None:
    extra = create(client, proposed_rule=rule_doc())
    assert extra.status_code == 422 and paths(extra) == ["proposed_rule"]
    bad = create(client, kind="threshold", proposed_rule=rule_doc() | {"when": {"nope": 1}})
    assert bad.status_code == 422 and any(p.startswith("body.proposed_rule") for p in paths(bad))
    assert env.rows == {} and env.published == []


def test_list_filters_and_order_passthrough(client: TestClient, env: Env) -> None:
    create(client)
    assert len(client.get("/api/v1/fix-proposals?team=rates").json()) == 1
    assert client.get("/api/v1/fix-proposals?team=other").json() == []
    assert client.get("/api/v1/fix-proposals?status=accepted").json() == []
    assert env.listed[-1] == (None, ProposalStatus.accepted)
    assert client.get("/api/v1/fix-proposals?status=bogus").status_code == 422


def test_accept_rule_saves_once_then_marks_then_publishes(client: TestClient, env: Env) -> None:
    create(client, kind="threshold", proposed_rule=rule_doc("New title"))
    env.events.clear()
    env.published.clear()
    response = decide(client, "accept")
    assert response.status_code == 200 and response.json()["status"] == "accepted"
    assert [r.present.title for r in env.saved_rules] == ["New title"]
    assert env.events.index("save_rule") < env.events.index("mark") < env.events.index("commit")
    assert env.events.index("commit") < env.events.index("publish")
    assert env.audits[-1]["detail"]["decision"] == "accept"
    assert env.audits[-1]["detail"]["comment"] == "why"
    assert env.audits[-1]["detail"]["version"] == 7
    assert env.published[0] == "rates:fix_proposal.updated"
    assert len(env.published) == 4


def test_accept_runbook_step_shifts_indexes(client: TestClient, env: Env) -> None:
    create(client, kind="runbook_step", proposed_runbook_step=step_doc(1, "inserted"))
    assert decide(client, "accept").status_code == 200
    saved = env.saved_runbooks[0]
    assert [(s.index, s.text) for s in saved.steps] == [
        (0, "a"),
        (1, "inserted"),
        (2, "b"),
        (3, "c"),
    ]
    assert env.rows[PROPOSAL_ID].status is ProposalStatus.accepted


def test_accept_runbook_step_beyond_end_appends(client: TestClient, env: Env) -> None:
    create(client, kind="runbook_step", proposed_runbook_step=step_doc(99, "last"))
    decide(client, "accept")
    assert [s.index for s in env.saved_runbooks[0].steps] == [0, 1, 2, 3]
    assert env.saved_runbooks[0].steps[-1].text == "last"


def test_accept_missing_runbook_is_422_and_nothing_marked(client: TestClient, env: Env) -> None:
    create(client, kind="runbook_step", proposed_runbook_step=step_doc(1))
    env.runbook = None
    env.published.clear()
    response = decide(client, "accept")
    assert response.status_code == 422
    assert env.rows[PROPOSAL_ID].status is ProposalStatus.pending
    assert "mark" not in env.events and env.published == []


def test_reject_changes_only_status(client: TestClient, env: Env) -> None:
    create(client, kind="threshold", proposed_rule=rule_doc("New"))
    response = decide(client, "reject")
    assert response.status_code == 200 and response.json()["status"] == "rejected"
    assert env.saved_rules == [] and env.saved_runbooks == []
    assert env.audits[-1]["verb"].value == "fix_decided"
    assert env.audits[-1]["detail"]["decision"] == "reject"


def test_second_decision_is_409_and_publishes_nothing(client: TestClient, env: Env) -> None:
    create(client)
    decide(client, "reject")
    env.published.clear()
    env.saved_rules.clear()
    response = decide(client, "accept")
    assert response.status_code == 409
    assert ErrorResponse.model_validate(response.json()).error == "already_decided"
    assert env.published == [] and env.saved_rules == []


def test_unknown_or_malformed_proposal_is_404(client: TestClient, env: Env) -> None:
    assert decide(client, "reject").status_code == 404
    assert decide(client, "reject", "not-a-uuid").status_code == 404


def test_save_failure_marks_nothing_and_publishes_nothing(env: Env) -> None:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    app.dependency_overrides[get_pool] = lambda: FakePool(env)
    app.dependency_overrides[get_redis] = lambda: object()
    app.dependency_overrides[get_registry] = lambda: None
    app.dependency_overrides[get_catalog] = lambda: SimpleNamespace(get=lambda _id: env.runbook)
    with TestClient(app, raise_server_exceptions=False) as client:
        create(client, kind="threshold", proposed_rule=rule_doc("New"))
        env.fail_save = True
        env.published.clear()
        response = decide(client, "accept")
    assert response.status_code == 500
    assert env.rows[PROPOSAL_ID].status is ProposalStatus.pending
    assert "mark" not in env.events and "rollback" in env.events
    assert env.published == []


def test_proposal_cannot_change_rule_ownership(client: TestClient, env: Env) -> None:
    response = create(client, kind="threshold", proposed_rule=rule_doc(team="other"))
    assert response.status_code == 422 and paths(response) == ["proposed_rule.team"]
    assert env.rows == {} and env.published == []


def _crashing_client(env: Env) -> TestClient:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    app.dependency_overrides[get_pool] = lambda: FakePool(env)
    app.dependency_overrides[get_redis] = lambda: object()
    app.dependency_overrides[get_registry] = lambda: None
    app.dependency_overrides[get_catalog] = lambda: SimpleNamespace(get=lambda _id: env.runbook)
    return TestClient(app, raise_server_exceptions=False)


def test_reaccept_after_crash_between_save_and_mark_saves_rule_once(env: Env) -> None:
    with _crashing_client(env) as client:
        create(client, kind="threshold", proposed_rule=rule_doc("New"))
        env.fail_mark = True
        assert decide(client, "accept").status_code == 500
        assert env.rows[PROPOSAL_ID].status is ProposalStatus.pending
        env.fail_mark = False
        response = decide(client, "accept")
    assert response.status_code == 200 and response.json()["status"] == "accepted"
    assert len(env.saved_rules) == 1
    assert env.audits[-1]["detail"]["version"] == 7


def test_reaccept_after_crash_saves_runbook_step_once(env: Env) -> None:
    with _crashing_client(env) as client:
        create(client, kind="runbook_step", proposed_runbook_step=step_doc(1, "inserted"))
        env.fail_mark = True
        assert decide(client, "accept").status_code == 500
        env.fail_mark = False
        assert decide(client, "accept").status_code == 200
    assert len(env.saved_runbooks) == 1
    assert [s.text for s in env.runbook.steps] == ["a", "inserted", "b", "c"]
