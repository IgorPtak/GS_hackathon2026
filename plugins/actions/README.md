# plugins/actions

Action plugins run individual runbook steps against external HTTP targets or the mock gateway.
Each action is configured in `config/actions/<id>.yaml` and validated against
[`contracts/schemas/config.ActionConfig.schema.json`](../../contracts/schemas/config.ActionConfig.schema.json).

Plugins return `ActionResult(is_success, detail, data)`; business failures (missing required
params, timeouts, non-2xx responses, and HTTP transport errors) are returned as failed results
rather than raised as exceptions. Request timeouts come from `timeout:` in the action YAML.

## Add a webhook action (YAML only)

Most HTTP actions need no Python code—use `type: webhook` and add `config/actions/page-oncall.yaml`:

```yaml
id: page-oncall
type: webhook
approval: required
timeout: 10s
params:
  reason: { description: Why we page }
settings:
  url: "http://mock-gateway:8090/webhooks/pages"   # {{param}} is URL-encoded
  method: POST                                      # default: POST
  headers: { Content-Type: application/json }
  body_template: '{"reason": "{{reason}}"}'         # JSON-escaped when starting with { or [
```

- `approval` defaults to `none`; set `approval: required` so the runbook runner creates a pending
  approval request and waits for human approval before the action run starts.
- Entries under `params` have `is_required: true` by default; set `is_required: false` for
  optional parameters.
- When `body_template` starts with `{` or `[`, template values are JSON-escaped automatically and
  `Content-Type: application/json` is added if no `Content-Type` header is set.

## Add a new action plugin (under ten lines)

1. Create `plugins/actions/ping.py`, subclass `ActionPlugin`, set `type`, implement `_run`, and
   decorate with `@register_action_plugin`:

```python
from alerting_contracts.config import ActionConfig
from plugins.actions.base import ActionPlugin, ActionResult
from plugins.actions.registry import register_action_plugin


@register_action_plugin
class PingAction(ActionPlugin):
    type = "ping"

    async def _run(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        return await self.send("GET", params["url"], config)
```

2. Import the module in `plugins/actions/__init__.py` so importing `plugins.actions` registers it:

```python
from plugins.actions import (  # noqa: F401
    ...,
    ping,
)
```

3. Configure an action in `config/actions/ping-service.yaml` and reference `ping-service` from a
   runbook step:

```yaml
id: ping-service
type: ping
description: Check that a service endpoint responds with 2xx
approval: none
timeout: 5s
params:
  url: { description: Target URL to ping }
```

## Plugin contract

Defined in `plugins/actions/base.py` and `plugins/actions/registry.py`:

- `ActionPlugin.type: str` — registry key matching `ActionConfig.type`.
- `ActionPlugin.__init__(self, client: httpx.AsyncClient | None = None)` — accepts an injectable
  `httpx.AsyncClient` for tests; otherwise `send()` creates one per call.
- `async ActionPlugin.execute(self, params: dict[str, str], config: ActionConfig) -> ActionResult` —
  public entry point. Validates required params (`config.params[*].is_required`) via
  `ActionPlugin.missing_required(params, config)` before any I/O, invokes
  `await self._run(params, config)`, and converts any uncaught `httpx.HTTPError` into a failed
  `ActionResult`.
- `async ActionPlugin._run(self, params: dict[str, str], config: ActionConfig) -> ActionResult` —
  abstract method implemented by subclasses after required params are validated.
- `async ActionPlugin.send(self, method: str, url: str, config: ActionConfig, *, headers: dict[str, str] | None = None, content: str | None = None) -> ActionResult` —
  issues one HTTP request using `config.timeout` (parsed by `parse_duration_seconds`), records
  `{"status_code": ..., "elapsed_ms": ...}` in `ActionResult.data`, and maps timeouts,
  `httpx.HTTPError`, and non-2xx status codes to `ActionResult(is_success=False, ...)`.
- `ActionResult(is_success: bool, detail: str, data: dict[str, Any] = {})` — outcome model;
  `data` is stored in `ActionRun.result`.
- Registry (`plugins/actions/registry.py`): `@register_action_plugin`,
  `get_action_plugin(type: str) -> ActionPlugin` (raises `UnknownActionTypeError` for unknown
  types), and `registered_types() -> list[str]`.
- Shared helpers: `render_url(template, params)`, `render_template(template, params, *, json_escape=False)`,
  `parse_duration_seconds(value)`, and `mock_gateway_url()` (reads `MOCK_GATEWAY_URL`, default
  `http://mock-gateway:8090`) in `base.py`; `call_webhook(plugin, params, config, settings)` in
  `webhook.py`.

## Built-in action plugins

| Type | Module | Behavior | Demo config (`config/actions/`) |
|---|---|---|---|
| `webhook` | `webhook.py` | YAML-driven HTTP call using `settings` (`url`, `method`, `headers`, `body_template`). | `escalate.yaml`, `open-ticket.yaml`, `restart-pricing-adapter.yaml` |
| `http_get` | `http_get.py` | Sends `GET` to `params["url"]`; succeeds on 2xx. | `http-health-check.yaml` |
| `retry_workflow` | `retry_workflow.py` | Sends `POST {settings.base_url}/{workflow_id}/retry` (default `{MOCK_GATEWAY_URL}/workflows`). | `retry-workflow.yaml` |
| `restart_service` | `restart_service.py` | Delegates to `call_webhook` if `settings.url` is set; else `POST {MOCK_GATEWAY_URL}/services/{service}/restart` from `params["service"]` or `settings["service"]`. | — |
| `open_ticket` | `open_ticket.py` | Delegates to `call_webhook` if `settings.url` and `settings.body_template` are set; else `POST {settings.url or MOCK_GATEWAY_URL + "/tickets"}` with JSON `summary` and remaining `params`. | — |
| `escalate` | `escalate.py` | Delegates to `call_webhook` if `settings.url` is set; else `POST {MOCK_GATEWAY_URL}/webhooks/escalations` with JSON `params`. | — |

## Tests

From the repository root:

```bash
uv run pytest plugins/actions/tests -q
```
