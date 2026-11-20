"""api skeleton tests; Redis and Postgres are faked through dependency overrides."""

from pathlib import Path
from typing import Any

import orjson
import pytest
import yaml
from alerting_contracts.api import ErrorResponse
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.dependencies import get_redis
from services.api.main import create_app

ROOT = Path(__file__).resolve().parents[3]


class FakeRedis:
    """Minimal xrevrange over a list of (id, fields), newest first, max inclusive."""

    def __init__(self, entries: list[tuple[bytes, dict[bytes, bytes]]]) -> None:
        self.entries = entries

    async def xrevrange(self, name: str, max: str = "+", min: str = "-", count: int | None = None):
        assert name == "events"
        out = [e for e in self.entries if max == "+" or e[0].decode() <= max]
        return out[:count]


def entry(n: int, source_id: str) -> tuple[bytes, dict[bytes, bytes]]:
    envelope = {
        "event_id": f"e{n}",
        "source_id": source_id,
        "source_type": "webhook",
        "received_at": "2026-01-01T00:00:00Z",
        "payload": {"n": n},
    }
    return f"{n:04d}-0".encode(), {b"envelope": orjson.dumps(envelope)}


def make_client(
    redis: Any = None, config_dir: str = str(ROOT / "config"), *, raise_errors: bool = True
) -> TestClient:
    app = create_app(Settings(config_dir=config_dir, database_url="postgresql://x@127.0.0.1:1/x"))
    if redis is not None:
        app.dependency_overrides[get_redis] = lambda: redis
    return TestClient(app, raise_server_exceptions=raise_errors)


def test_healthz() -> None:
    with make_client() as client:
        assert client.get("/healthz").json() == {"status": "ok"}


def test_config_has_four_teams() -> None:
    with make_client() as client:
        body = client.get("/api/v1/config").json()
    assert len(body["teams"]) == 4
    assert body["sources"] and body["channels"]


def test_events_recent_newest_first_and_limit() -> None:
    fake = FakeRedis([entry(n, "a") for n in range(10, 0, -1)])
    with make_client(fake) as client:
        body = client.get("/api/v1/events/recent?limit=3").json()
    assert [e["event_id"] for e in body] == ["e10", "e9", "e8"]


def test_events_recent_source_filter_scans_back() -> None:
    entries = [entry(n, "b" if n > 3 else "a") for n in range(10, 0, -1)]
    with make_client(FakeRedis(entries)) as client:
        body = client.get("/api/v1/events/recent?source_id=a&limit=2").json()
    assert [e["event_id"] for e in body] == ["e3", "e2"]


def test_events_recent_limit_too_big_is_error_response() -> None:
    with make_client(FakeRedis([])) as client:
        response = client.get("/api/v1/events/recent?limit=501")
    assert response.status_code == 422
    assert ErrorResponse.model_validate(response.json()).error == "validation_failed"


def test_not_found_is_error_response() -> None:
    with make_client() as client:
        response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_unexpected_error_hides_traceback() -> None:
    class Boom:
        async def xrevrange(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("secret detail")

    with make_client(Boom(), raise_errors=False) as client:
        response = client.get("/api/v1/events/recent")
    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_error",
        "message": "internal server error",
        "details": [],
    }


@pytest.mark.parametrize("exempt", [{"/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"}])
def test_routes_exist_in_openapi_spec(exempt: set[str]) -> None:
    spec = yaml.safe_load((ROOT / "contracts" / "openapi.yaml").read_text())["paths"]
    app = create_app(Settings())
    for route in app.routes:
        path = getattr(route, "path", "")
        if path in exempt or path == "/metrics":
            continue
        for method in getattr(route, "methods", None) or ():
            if method in {"HEAD", "OPTIONS"}:
                continue
            assert method.lower() in spec.get(path, {}), f"{method} {path} not in openapi.yaml"


def test_db_less_start_falls_back_to_directory_source() -> None:
    with make_client() as client:
        assert type(client.app.state.config_source).__name__ == "DirectoryConfigSource"  # type: ignore[attr-defined]
        assert client.app.state.registry is None  # type: ignore[attr-defined]


def test_config_served_from_registry_source() -> None:
    from alerting_contracts.config import Team

    from services.api.config_source import DirectoryConfigSource, RegistryConfigSource

    lists = DirectoryConfigSource(str(ROOT / "config")).get_config_lists()

    class FakeRegistry:
        def teams(self) -> dict[str, Team]:
            return {t.id: t for t in lists.teams[:2]}

        def recipients(self) -> dict[str, Any]:
            return {}

        channels = actions = sources = recipients

    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    with TestClient(app) as client:
        client.app.state.config_source = RegistryConfigSource(FakeRegistry())  # type: ignore[arg-type,attr-defined]
        body = client.get("/api/v1/config").json()
    assert len(body["teams"]) == 2 and body["channels"] == []


def test_empty_registry_falls_back_to_directory() -> None:
    from services.api.config_source import DirectoryConfigSource, RegistryConfigSource

    class EmptyRegistry:
        def teams(self) -> dict[str, Any]:
            return {}

        recipients = channels = actions = sources = teams

    source = RegistryConfigSource(
        EmptyRegistry(),  # type: ignore[arg-type]
        fallback=DirectoryConfigSource(str(ROOT / "config")),
    )
    assert len(source.get_config_lists().teams) == 4
    assert RegistryConfigSource(EmptyRegistry()).get_config_lists().teams == []  # type: ignore[arg-type]
