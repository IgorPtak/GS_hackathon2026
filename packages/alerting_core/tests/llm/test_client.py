"""Tests for LlmClient."""

import json

import httpx
import pytest
import respx
from alerting_core.llm import (
    InMemoryLlmCache,
    LlmClient,
    LlmConfig,
    LlmHostNotAllowedError,
    LlmOutputInvalidError,
    LlmUnavailableError,
)

from .conftest import Answer, chat

URL = "http://localhost:11434/v1/chat/completions"


@respx.mock
@pytest.mark.asyncio
async def test_success_and_body_shape(config: LlmConfig) -> None:
    route = respx.post(URL).respond(200, json=chat('{"value": 3}'))
    result = await LlmClient(config).generate("hi", Answer, system="sys")
    assert result == Answer(value=3)
    request = route.calls.last.request
    body = json.loads(request.content)
    assert body["model"] == "m"
    assert body["temperature"] == 0
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "answer",
            "schema": Answer.model_json_schema(),
            "strict": False,
        },
    }
    assert request.headers["authorization"] == "Bearer sk-test-key-123456"


@respx.mock
@pytest.mark.asyncio
async def test_think_stripped(config: LlmConfig) -> None:
    respx.post(URL).respond(200, json=chat('<think>\nhmm\n</think>\n{"value": 1}'))
    assert await LlmClient(config).generate("x", Answer) == Answer(value=1)


@respx.mock
@pytest.mark.asyncio
async def test_retry_then_success(config: LlmConfig) -> None:
    route = respx.post(URL).mock(
        side_effect=[
            httpx.Response(200, json=chat('{"value": "no"}')),
            httpx.Response(200, json=chat('{"value": 2}')),
        ]
    )
    assert await LlmClient(config).generate("x", Answer) == Answer(value=2)
    messages = json.loads(route.calls.last.request.content)["messages"]
    assert messages[-2] == {"role": "assistant", "content": '{"value": "no"}'}
    assert messages[-1]["role"] == "user"
    assert "validation" in messages[-1]["content"]


@respx.mock
@pytest.mark.asyncio
async def test_double_invalid(config: LlmConfig) -> None:
    route = respx.post(URL).respond(200, json=chat("not json"))
    with pytest.raises(LlmOutputInvalidError):
        await LlmClient(config).generate("x", Answer)
    assert route.call_count == 2


@respx.mock
@pytest.mark.asyncio
async def test_timeout(config: LlmConfig) -> None:
    respx.post(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(LlmUnavailableError):
        await LlmClient(config).generate("x", Answer)


@respx.mock
@pytest.mark.asyncio
async def test_connection_error_and_non_2xx(config: LlmConfig) -> None:
    respx.post(URL).mock(side_effect=httpx.ConnectError("down"))
    with pytest.raises(LlmUnavailableError):
        await LlmClient(config).generate("x", Answer)
    respx.post(URL).respond(500)
    with pytest.raises(LlmUnavailableError):
        await LlmClient(config).generate("x", Answer)


@respx.mock
@pytest.mark.asyncio
async def test_host_not_allowed() -> None:
    route = respx.post("https://evil.example/v1/chat/completions").respond(
        200, json=chat("{}")
    )
    with pytest.raises(LlmHostNotAllowedError):
        LlmClient(LlmConfig(base_url="https://evil.example/v1"))
    assert route.call_count == 0


@respx.mock
@pytest.mark.asyncio
async def test_outgoing_body_has_no_secret(config: LlmConfig) -> None:
    route = respx.post(URL).respond(200, json=chat('{"value": 1}'))
    await LlmClient(config).generate(
        "password=hunter2 card 4111 1111 1111 1111",
        Answer,
        system="Authorization: Bearer abcdef1234567890",
    )
    raw = route.calls.last.request.content.decode()
    for secret in ("hunter2", "4111", "abcdef1234567890"):
        assert secret not in raw


@respx.mock
@pytest.mark.asyncio
async def test_cache_hit_skips_http(config: LlmConfig) -> None:
    route = respx.post(URL).respond(200, json=chat('{"value": 5}'))
    client = LlmClient(config, cache=InMemoryLlmCache())
    first = await client.generate("same", Answer)
    second = await client.generate("same", Answer)
    assert first == second == Answer(value=5)
    assert route.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_no_authorization_without_key() -> None:
    route = respx.post(URL).respond(200, json=chat('{"value": 1}'))
    await LlmClient(LlmConfig(base_url="http://localhost:11434/v1")).generate(
        "x", Answer
    )
    assert "authorization" not in route.calls.last.request.headers


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "7")
    monkeypatch.setenv("LLM_ALLOWED_HOSTS", "127.0.0.1, foo")
    cfg = LlmConfig.from_env()
    assert cfg.api_key is None
    assert cfg.timeout_seconds == 7
    assert cfg.allowed_hosts == ("127.0.0.1", "foo")
