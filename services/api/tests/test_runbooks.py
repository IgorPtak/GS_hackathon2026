"""Runbook routes with the config directory real and storage faked (no database)."""

from pathlib import Path
from typing import Any

import pytest
from alerting_contracts.api import ErrorResponse, RunbookSummary
from alerting_contracts.runbooks import Runbook
from alerting_core.settings import Settings
from fastapi.testclient import TestClient

from services.api.dependencies import get_pool, get_redis
from services.api.main import create_app
from services.api.routers import runbooks as runbooks_router

FIXTURES = Path("contracts/fixtures/runbooks")
ACTOR = {"id": "anna"}


@pytest.fixture
def client() -> TestClient:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x", config_dir="config"))
    app.dependency_overrides[get_pool] = lambda: object()
    app.dependency_overrides[get_redis] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client


def test_list_falls_back_to_files(client: TestClient) -> None:
    body = client.get("/api/v1/runbooks").json()
    summaries = [RunbookSummary.model_validate(item) for item in body]
    assert {s.id for s in summaries} == {
        "workflow-failed",
        "trade-limit-breach",
        "pricing-stale-feed",
    }
    assert all(s.step_count >= 1 and s.version == 1 for s in summaries)


def test_get_includes_source_and_404(client: TestClient) -> None:
    runbook = Runbook.model_validate(client.get("/api/v1/runbooks/workflow-failed").json())
    assert runbook.source and runbook.format == "yaml"
    response = client.get("/api/v1/runbooks/nope")
    assert response.status_code == 404
    assert ErrorResponse.model_validate(response.json()).error == "not_found"


@pytest.mark.parametrize(
    ("file", "format", "normalized_by"),
    [
        ("workflow-failed.yaml", "yaml", "parser"),
        ("trade-limit-breach.md", "markdown", "parser"),
        ("pricing-stale-feed.txt", "text", "fallback"),
    ],
)
def test_normalize_preview_all_formats(
    client: TestClient, file: str, format: str, normalized_by: str
) -> None:
    source = (FIXTURES / file).read_text()
    response = client.post("/api/v1/runbooks/normalize", json={"format": format, "source": source})
    assert response.status_code == 200
    runbook = Runbook.model_validate(response.json())
    assert runbook.id == "preview" and runbook.normalized_by == normalized_by
    assert runbook.source == source and runbook.steps


def test_normalize_invalid_yaml_is_422_with_details(client: TestClient) -> None:
    source = "id: x\ntitle: t\nsteps:\n  - index: 0\n    kind: bogus\n    text: hi\n"
    response = client.post("/api/v1/runbooks/normalize", json={"format": "yaml", "source": source})
    assert response.status_code == 422
    error = ErrorResponse.model_validate(response.json())
    assert error.error == "validation_failed"
    assert any(d.path.startswith("steps.0.kind") for d in error.details)


def test_normalize_not_a_mapping_and_empty_source(client: TestClient) -> None:
    response = client.post(
        "/api/v1/runbooks/normalize", json={"format": "yaml", "source": "- just\n- a list"}
    )
    assert response.status_code == 422 and response.json()["details"]
    assert (
        client.post("/api/v1/runbooks/normalize", json={"format": "text", "source": ""}).status_code
        == 422
    )


def put_body(**overrides: Any) -> dict[str, Any]:
    body = {
        "id": "rb-1",
        "title": "RB",
        "team": None,
        "format": "markdown",
        "source": (FIXTURES / "trade-limit-breach.md").read_text(),
        "actor": ACTOR,
    }
    return body | overrides


def test_put_saves_and_returns_version(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    saved: list[Runbook] = []

    async def fake_save(pool: Any, redis: Any, runbook: Runbook, actor: Any) -> int:
        saved.append(runbook)
        return 4

    monkeypatch.setattr(runbooks_router, "save_runbook", fake_save)
    response = client.put("/api/v1/runbooks/rb-1", json=put_body())
    assert response.status_code == 200
    assert response.json()["version"] == 4 and response.json()["id"] == "rb-1"
    assert len(saved) == 1 and saved[0].title == "RB"


def test_put_id_mismatch_is_422(client: TestClient) -> None:
    assert client.put("/api/v1/runbooks/other", json=put_body()).status_code == 422


def test_put_invalid_source_is_422(client: TestClient) -> None:
    response = client.put("/api/v1/runbooks/rb-1", json=put_body(format="yaml", source="[]"))
    assert response.status_code == 422 and response.json()["details"]


def test_put_without_database_is_503() -> None:
    app = create_app(Settings(database_url="postgresql://x@127.0.0.1:1/x"))
    with TestClient(app) as test_client:
        response = test_client.put("/api/v1/runbooks/rb-1", json=put_body())
    assert response.status_code == 503


class FakeLlm:
    model = "fake-model"

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def generate(self, prompt: str, response_model: Any, *, system: str | None = None) -> Any:
        self.calls += 1
        if self.error:
            raise self.error
        return response_model.model_validate(
            {
                "steps": [
                    {"index": 0, "kind": "check", "text": "Check feed"},
                    {
                        "index": 1,
                        "kind": "action",
                        "text": "Restart {{feed}}",
                        "action": "restart-pricing-adapter",
                        "params": {"feed": "{{feed}}"},
                    },
                ]
            }
        )


def _put_with_llm(client: TestClient, monkeypatch: pytest.MonkeyPatch, llm: Any, **overrides: Any):
    async def fake_save(pool: Any, redis: Any, runbook: Runbook, actor: Any) -> int:
        return 1

    monkeypatch.setattr(runbooks_router, "save_runbook", fake_save)
    client.app.state.llm = llm
    return client.put("/api/v1/runbooks/rb-1", json=put_body(**overrides))


def test_put_text_uses_llm(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    llm = FakeLlm()
    response = _put_with_llm(
        client,
        monkeypatch,
        llm,
        format="text",
        source=(FIXTURES / "pricing-stale-feed.txt").read_text(),
    )
    body = Runbook.model_validate(response.json())
    assert body.normalized_by == "llm" and body.llm_model == "fake-model"
    assert body.steps[1].approval == "required" and llm.calls == 1


def test_put_text_llm_error_falls_back(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from alerting_core.llm import LlmUnavailableError

    response = _put_with_llm(
        client, monkeypatch, FakeLlm(LlmUnavailableError("down")), format="text", source="do x"
    )
    assert response.status_code == 200
    assert response.json()["normalized_by"] == "fallback" and len(response.json()["steps"]) == 1


def test_put_markdown_and_yaml_use_parser_not_llm(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    llm = FakeLlm()
    response = _put_with_llm(client, monkeypatch, llm)
    assert response.json()["normalized_by"] == "parser"
    yaml_source = (FIXTURES / "workflow-failed.yaml").read_text()
    response = _put_with_llm(client, monkeypatch, llm, format="yaml", source=yaml_source)
    assert response.json()["normalized_by"] == "parser" and llm.calls == 0
