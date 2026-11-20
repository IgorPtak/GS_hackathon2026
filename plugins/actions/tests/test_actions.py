import json
from pathlib import Path

import httpx
import pytest
import respx
import yaml
from alerting_contracts.config import ActionConfig

from plugins.actions import UnknownActionTypeError, get_action_plugin
from plugins.actions.base import parse_duration_seconds

GW = "http://mock-gateway:8090"
CONFIG_DIR = Path(__file__).resolve().parents[3] / "config" / "actions"


def cfg(type_: str, params: dict | None = None, settings: dict | None = None, timeout="5s"):
    return ActionConfig.model_validate(
        {
            "id": "a1",
            "type": type_,
            "timeout": timeout,
            "params": params or {},
            "settings": settings or {},
        }
    )


@pytest.fixture(autouse=True)
def _gw(monkeypatch):
    monkeypatch.setenv("MOCK_GATEWAY_URL", GW)


def test_parse_duration():
    assert parse_duration_seconds("5s") == 5
    assert parse_duration_seconds("1m") == 60
    assert parse_duration_seconds("250ms") == 0.25


def test_unknown_type():
    with pytest.raises(UnknownActionTypeError):
        get_action_plugin("nope")


@pytest.mark.parametrize("path", sorted(CONFIG_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_every_demo_action_resolves(path):
    c = ActionConfig.model_validate(yaml.safe_load(path.read_text()))
    assert get_action_plugin(c.type).type == c.type


@pytest.mark.asyncio
@respx.mock
async def test_http_get_ok_and_non2xx():
    c = cfg("http_get", {"url": {}})
    respx.get("http://x/ok").respond(200)
    respx.get("http://x/bad").respond(503)
    r = await get_action_plugin("http_get").execute({"url": "http://x/ok"}, c)
    assert r.is_success and r.data["status_code"] == 200 and "elapsed_ms" in r.data
    r = await get_action_plugin("http_get").execute({"url": "http://x/bad"}, c)
    assert not r.is_success and r.data["status_code"] == 503


@pytest.mark.asyncio
@respx.mock
async def test_timeout_is_failure():
    respx.get("http://x/slow").mock(side_effect=httpx.ReadTimeout("t"))
    r = await get_action_plugin("http_get").execute({"url": "http://x/slow"}, cfg("http_get"))
    assert not r.is_success and "timeout" in r.detail


@pytest.mark.asyncio
@respx.mock
async def test_missing_required_param_no_call():
    route = respx.post(f"{GW}/tickets").respond(200)
    c = cfg("open_ticket", {"summary": {}, "team": {"is_required": False}})
    r = await get_action_plugin("open_ticket").execute({}, c)
    assert not r.is_success and "summary" in r.detail
    assert not route.called


@pytest.mark.asyncio
@respx.mock
async def test_retry_workflow():
    route = respx.post(f"{GW}/workflows/wf-1/retry").respond(202)
    c = cfg("retry_workflow", {"workflow_id": {}}, {"base_url": f"{GW}/workflows"})
    r = await get_action_plugin("retry_workflow").execute({"workflow_id": "wf-1"}, c)
    assert r.is_success and route.called
    respx.post(f"{GW}/workflows/wf-2/retry").respond(500)
    r = await get_action_plugin("retry_workflow").execute({"workflow_id": "wf-2"}, c)
    assert not r.is_success


@pytest.mark.asyncio
@respx.mock
async def test_restart_service_default_and_url():
    route = respx.post(f"{GW}/services/pricing/restart").respond(200)
    r = await get_action_plugin("restart_service").execute(
        {"service": "pricing"}, cfg("restart_service", {"service": {}})
    )
    assert r.is_success and route.called
    route2 = respx.post("http://h/r").respond(200)
    c = cfg("restart_service", settings={"url": "http://h/r"})
    assert (await get_action_plugin("restart_service").execute({}, c)).is_success
    assert route2.called


@pytest.mark.asyncio
@respx.mock
async def test_open_ticket_default():
    route = respx.post(f"{GW}/tickets").respond(201)
    r = await get_action_plugin("open_ticket").execute(
        {"summary": "boom"}, cfg("open_ticket", {"summary": {}})
    )
    assert r.is_success
    assert json.loads(route.calls[0].request.content)["summary"] == "boom"


@pytest.mark.asyncio
@respx.mock
async def test_escalate_with_url_and_failure():
    route = respx.post("http://h/esc").respond(200)
    c = cfg(
        "escalate",
        settings={"url": "http://h/esc", "body_template": '{"r": "{{reason}}"}'},
    )
    r = await get_action_plugin("escalate").execute({"reason": "x"}, c)
    assert r.is_success and json.loads(route.calls[0].request.content) == {"r": "x"}
    respx.post(f"{GW}/webhooks/escalations").respond(500)
    assert not (await get_action_plugin("escalate").execute({}, cfg("escalate"))).is_success


@pytest.mark.asyncio
@respx.mock
async def test_webhook_template_json_escaping_and_url_param():
    route = respx.post("http://h/hook/a%20b").respond(200)
    c = cfg(
        "webhook",
        {"msg": {}, "name": {}},
        {
            "url": "http://h/hook/{{name}}",
            "headers": {"X-Token": "t"},
            "body_template": '{"msg": "{{msg}}"}',
        },
    )
    r = await get_action_plugin("webhook").execute({"msg": 'say "hi"\nnow', "name": "a b"}, c)
    assert r.is_success
    req = route.calls[0].request
    assert json.loads(req.content) == {"msg": 'say "hi"\nnow'}
    assert req.headers["x-token"] == "t" and req.headers["content-type"] == "application/json"


@pytest.mark.asyncio
@respx.mock
async def test_webhook_default_method_plain_body_and_get():
    route = respx.post("http://h/p").respond(200)
    c = cfg("webhook", {"a": {}}, {"url": "http://h/p", "body_template": "a={{a}}"})
    await get_action_plugin("webhook").execute({"a": '"q"'}, c)
    assert route.calls[0].request.content == b'a="q"'
    g = respx.get("http://h/g").respond(200)
    c = cfg("webhook", settings={"url": "http://h/g", "method": "GET"})
    assert (await get_action_plugin("webhook").execute({}, c)).is_success and g.called


@pytest.mark.asyncio
@respx.mock
async def test_demo_webhook_actions_execute():
    for name, p, url in [
        ("open-ticket", {"summary": "s"}, f"{GW}/tickets"),
        (
            "restart-pricing-adapter",
            {"feed": "f"},
            f"{GW}/services/pricing-adapter/restart",
        ),
        ("escalate", {"workflow_id": "w"}, f"{GW}/webhooks/escalations"),
    ]:
        respx.post(url).respond(200)
        c = ActionConfig.model_validate(yaml.safe_load((CONFIG_DIR / f"{name}.yaml").read_text()))
        assert (await get_action_plugin(c.type).execute(p, c)).is_success, name
