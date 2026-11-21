"""LLM status endpoint: respx mocks the /models probe."""

import time
from types import SimpleNamespace

import httpx
import respx
from alerting_core.llm import LlmClient, LlmConfig
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.api.routers.llm_status import PRIVACY_NOTE, router

BASE = "http://localhost:11434/v1"
SECRET = "sk-super-secret-key"


def make_client(llm: LlmClient | None) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.state.llm = llm
    app.state.settings = SimpleNamespace()
    return TestClient(app)


def make_llm() -> LlmClient:
    return LlmClient(LlmConfig(base_url=BASE, api_key=SECRET, model="m1"))


def test_disabled_when_llm_is_none() -> None:
    body = make_client(None).get("/api/v1/llm/status").json()
    assert body["is_enabled"] is False
    assert body["is_reachable"] is None
    assert body["model"] is None
    assert body["provider_host"] is None
    assert body["latency_ms"] is None
    assert body["checked_at"] is None
    assert body["privacy_note"] == PRIVACY_NOTE


@respx.mock
def test_reachable_sends_auth_and_reports_host() -> None:
    route = respx.get(f"{BASE}/models").mock(return_value=httpx.Response(200, json={"data": []}))
    body = make_client(make_llm()).get("/api/v1/llm/status").json()
    assert body["is_enabled"] is True
    assert body["is_reachable"] is True
    assert body["model"] == "m1"
    assert body["provider_host"] == "localhost"
    assert isinstance(body["latency_ms"], int)
    assert body["checked_at"] is not None
    assert route.calls.last.request.headers["authorization"] == f"Bearer {SECRET}"


@respx.mock
def test_timeout_is_unreachable_but_200() -> None:
    respx.get(f"{BASE}/models").mock(side_effect=httpx.ConnectTimeout("slow"))
    response = make_client(make_llm()).get("/api/v1/llm/status")
    assert response.status_code == 200
    assert response.json()["is_reachable"] is False


@respx.mock
def test_http_error_status_is_unreachable() -> None:
    respx.get(f"{BASE}/models").mock(return_value=httpx.Response(401))
    assert make_client(make_llm()).get("/api/v1/llm/status").json()["is_reachable"] is False


@respx.mock
def test_second_call_within_60_seconds_uses_cache() -> None:
    route = respx.get(f"{BASE}/models").mock(return_value=httpx.Response(200, json={}))
    client = make_client(make_llm())
    first = client.get("/api/v1/llm/status").json()
    second = client.get("/api/v1/llm/status").json()
    assert route.call_count == 1
    assert first == second


@respx.mock
def test_expired_cache_probes_again() -> None:
    route = respx.get(f"{BASE}/models").mock(return_value=httpx.Response(200, json={}))
    client = make_client(make_llm())
    client.get("/api/v1/llm/status")
    started, status = client.app.state.llm_status_cache
    client.app.state.llm_status_cache = (time.monotonic() - 61, status)
    client.get("/api/v1/llm/status")
    assert route.call_count == 2


@respx.mock
def test_response_never_leaks_key_or_url() -> None:
    respx.get(f"{BASE}/models").mock(return_value=httpx.Response(200, json={}))
    text = make_client(make_llm()).get("/api/v1/llm/status").text
    assert SECRET not in text
    assert BASE not in text
    assert "11434" not in text
