"""Rules routes with an in-memory fake pool and Redis (no real database)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.dependencies import get_pool, get_redis
from services.api.main import create_app

ROOT = Path(__file__).resolve().parents[3]


class FakePool:
    """Emulates the few `config_documents` statements the rules routes issue."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict[str, Any]] = {}

    async def fetchrow(self, sql: str, *args: Any) -> dict[str, Any] | None:
        if sql.lstrip().startswith("INSERT INTO config_documents"):
            kind, doc_id, team, document, text, actor = args
            old = self.rows.get((kind, doc_id))
            version = old["version"] + 1 if old else 1
            self.rows[(kind, doc_id)] = {
                "id": doc_id, "team": team, "document": document, "yaml": text,
                "version": version, "updated_at": datetime.now(UTC), "updated_by": actor,
            }  # fmt: skip
            return {"version": version}
        if sql.startswith("DELETE"):
            row = self.rows.pop(("rule", args[0]), None)
            return {"version": row["version"]} if row else None
        return self.rows.get(("rule", args[0]))

    async def fetch(self, sql: str, team: str | None) -> list[dict[str, Any]]:
        rows = [r for (k, _), r in sorted(self.rows.items()) if k == "rule"]
        return [r for r in rows if team is None or r["team"] == team]


class FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> None:
        self.published.append((channel, payload))


RULE = yaml.safe_load((ROOT / "config/rules/platform-alertmanager.yaml").read_text())
ACTOR = {"id": "anna"}


def make() -> tuple[TestClient, FakePool, FakeRedis]:
    app = create_app(
        Settings(config_dir=str(ROOT / "config"), database_url="postgresql://x@127.0.0.1:1/x")
    )
    pool, redis = FakePool(), FakeRedis()
    app.dependency_overrides[get_pool] = lambda: pool
    app.dependency_overrides[get_redis] = lambda: redis
    return TestClient(app), pool, redis


def test_put_get_list_and_version_bump() -> None:
    client, _, redis = make()
    with client:
        r = client.put("/api/v1/rules/platform-alertmanager", json={"rule": RULE, "actor": ACTOR})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "rule" and body["version"] == 1
        assert yaml.safe_load(body["yaml"])["id"] == "platform-alertmanager"
        assert body["updated_by"]["id"] == "anna" and body["rule"]["team"] == "platform"
        changed = {**RULE, "description": "changed"}
        r2 = client.put(
            "/api/v1/rules/platform-alertmanager", json={"rule": changed, "actor": ACTOR}
        )
        assert r2.json()["version"] == 2
        assert client.get("/api/v1/rules/platform-alertmanager").json()["version"] == 2
        assert [x["id"] for x in client.get("/api/v1/rules").json()] == ["platform-alertmanager"]
        assert client.get("/api/v1/rules", params={"team": "nope"}).json() == []
        assert len(client.get("/api/v1/rules", params={"team": "platform"}).json()) == 1
    assert {c for c, _ in redis.published} == {"config.changed", "broadcast"}


def test_get_missing_is_404() -> None:
    client, _, _ = make()
    with client:
        r = client.get("/api/v1/rules/nope")
    assert r.status_code == 404 and r.json()["error"] == "not_found"


def test_put_id_mismatch_is_422() -> None:
    client, pool, _ = make()
    with client:
        r = client.put("/api/v1/rules/other", json={"rule": RULE, "actor": ACTOR})
    assert r.status_code == 422 and r.json()["error"] == "validation_failed"
    assert r.json()["details"][0]["path"] == "rule.id"
    assert not pool.rows


def test_put_invalid_rule_has_dot_path_details() -> None:
    client, pool, _ = make()
    bad = {**RULE, "when": {"all": [{"field": "a", "op": "bogus", "value": 1}]}}
    with client:
        r = client.put("/api/v1/rules/platform-alertmanager", json={"rule": bad, "actor": ACTOR})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_failed"
    assert body["details"] and all({"path", "message"} <= set(d) for d in body["details"])
    assert any(d["path"].startswith("rule.when.all.0") for d in body["details"])
    assert not pool.rows


def test_delete_publishes_and_404s() -> None:
    client, pool, redis = make()
    with client:
        client.put("/api/v1/rules/platform-alertmanager", json={"rule": RULE, "actor": ACTOR})
        redis.published.clear()
        r = client.delete("/api/v1/rules/platform-alertmanager")
        assert r.status_code == 204 and not pool.rows
        assert len(redis.published) == 2
        assert client.delete("/api/v1/rules/platform-alertmanager").status_code == 404


def test_503_without_database() -> None:
    app = create_app(
        Settings(config_dir=str(ROOT / "config"), database_url="postgresql://x@127.0.0.1:1/x")
    )
    with TestClient(app) as client:
        r = client.get("/api/v1/rules")
    assert r.status_code == 503 and r.json()["error"] == "unavailable"
