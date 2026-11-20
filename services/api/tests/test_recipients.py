"""PUT /recipients/{id}/channel-preferences with a fake registry and a recorded save."""

from types import SimpleNamespace
from typing import Any

import pytest
from alerting_contracts.config import Recipient
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.dependencies import get_pool, get_redis, get_registry
from services.api.main import create_app
from services.api.routers import recipients as recipients_router

ACTOR = {"id": "anna"}
URL = "/api/v1/recipients/anna/channel-preferences"
PREFERENCE = {
    "when": {"severities": ["critical"], "sources": []},
    "channels": ["email"],
    "working_hours": "08:00-20:00",
    "timezone": "Europe/Warsaw",
    "otherwise": ["sms"],
}


class FakePool:
    """config_documents as a dict; `fetchval` returns the stored JSON like asyncpg does."""

    def __init__(self) -> None:
        self.documents: dict[str, str] = {}

    async def fetchval(self, _query: str, recipient_id: str) -> str | None:
        return self.documents.get(recipient_id)


class Env:
    def __init__(self) -> None:
        self.saved: list[tuple[str, Recipient, Any]] = []
        self.pool = FakePool()
        self.recipient = Recipient.model_validate(
            {"id": "anna", "display_name": "Anna", "teams": ["rates"]}
        )


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Env:
    state = Env()

    async def save(_pool: Any, _redis: Any, kind: str, document: Recipient, actor: Any) -> int:
        state.saved.append((kind, document, actor))
        state.pool.documents[document.id] = document.model_dump_json()
        return len(state.saved)

    monkeypatch.setattr(recipients_router, "save_config_document", save)
    return state


@pytest.fixture
def client(env: Env) -> TestClient:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    # main.py registers the router; including it here keeps the test independent of that.
    if not any(getattr(r, "path", "") == URL.replace("anna", "{recipient_id}") for r in app.routes):
        app.include_router(recipients_router.router)
    app.dependency_overrides[get_pool] = lambda: env.pool
    app.dependency_overrides[get_redis] = lambda: object()
    # recipients()/channels() are methods on the real registry; the fake must be callable too.
    registry = SimpleNamespace(
        recipients=lambda: {"anna": env.recipient},
        channels=lambda: {"email": object(), "sms": object(), "ui": object()},
    )
    app.dependency_overrides[get_registry] = lambda: registry
    with TestClient(app) as test_client:
        yield test_client


def put(client: TestClient, preferences: list[dict[str, Any]], recipient: str = "anna") -> Any:
    url = f"/api/v1/recipients/{recipient}/channel-preferences"
    return client.put(url, json={"channel_preferences": preferences, "actor": ACTOR})


def test_unknown_recipient_is_404(client: TestClient, env: Env) -> None:
    r = put(client, [PREFERENCE], recipient="nobody")
    assert r.status_code == 404 and r.json()["error"] == "not_found"
    assert env.saved == []


def test_unknown_channel_is_422_with_path(client: TestClient, env: Env) -> None:
    bad = {**PREFERENCE, "channels": ["email", "pager"]}
    r = put(client, [PREFERENCE, bad])
    assert r.status_code == 422
    assert [d["path"] for d in r.json()["details"]] == ["channel_preferences.1.channels.1"]
    bad_otherwise = {**PREFERENCE, "otherwise": ["pager"]}
    r2 = put(client, [bad_otherwise])
    assert r2.json()["details"][0]["path"] == "channel_preferences.0.otherwise.0"
    assert env.saved == []


def test_bad_timezone_is_422(client: TestClient, env: Env) -> None:
    r = put(client, [{**PREFERENCE, "timezone": "Mars/Base"}])
    assert r.status_code == 422
    assert r.json()["details"][0]["path"] == "channel_preferences.0.timezone"
    assert env.saved == []


def test_bad_working_hours_is_422(client: TestClient, env: Env) -> None:
    r = put(client, [{**PREFERENCE, "working_hours": "8-20"}])
    assert r.status_code == 422
    assert r.json()["details"][0]["path"] == "channel_preferences.0.working_hours"


def test_unchanged_saves_nothing(client: TestClient, env: Env) -> None:
    env.recipient = Recipient.model_validate(
        {"id": "anna", "display_name": "Anna", "channel_preferences": [PREFERENCE]}
    )
    r = put(client, [PREFERENCE])
    assert r.status_code == 200
    assert r.json()["channel_preferences"][0]["channels"] == ["email"]
    assert env.saved == []


def test_changed_is_saved_once_and_returned(client: TestClient, env: Env) -> None:
    r = put(client, [PREFERENCE])
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "anna" and body["teams"] == ["rates"]
    assert body["channel_preferences"][0]["working_hours"] == "08:00-20:00"
    assert len(env.saved) == 1
    kind, document, actor = env.saved[0]
    assert kind == "recipient" and document.channel_preferences[0].otherwise == ["sms"]
    assert actor.id == "anna"


def test_repeat_put_saves_once_while_registry_is_stale(client: TestClient, env: Env) -> None:
    # The registry still holds the old recipient (config.changed not applied yet).
    first = put(client, [PREFERENCE])
    second = put(client, [PREFERENCE])
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(env.saved) == 1
