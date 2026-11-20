# plugins/actions

Action plugins: base interface, registry, one file per action type. Webhook actions need only YAML.

Owner: track B. Tasks: B-10. See `docs/IMPLEMENTATION_PLAN.md`.

Plugins return `ActionResult(is_success, detail, data)`; business failures (non-2xx, timeout,
missing required params) are results, never exceptions. Timeout comes from `timeout:` in the YAML.

## Add a webhook action in under ten lines

`config/actions/page-oncall.yaml`, no code:

```yaml
id: page-oncall
type: webhook
approval: required
timeout: 10s
params:
  reason: { description: Why we page }
settings:
  url: "http://mock-gateway:8090/webhooks/pages"   # may contain {{param}}
  method: POST                                      # default POST
  headers: { Content-Type: application/json }
  body_template: '{"reason": "{{reason}}"}'         # values are JSON-escaped for JSON templates
```

## Add a plugin

One file `plugins/actions/<type>.py`, one decorator, import it in `__init__.py`:

```python
from plugins.actions.base import ActionPlugin, ActionResult
from plugins.actions.registry import register_action_plugin


@register_action_plugin
class PingAction(ActionPlugin):
    type = "ping"

    async def _run(self, params, config) -> ActionResult:
        return await self.send("GET", params["url"], config)
```

Run tests (from repo root): see the pytest command in the B-10 brief
(`PYTHONPATH=contracts:. ... python -m pytest plugins/actions/tests -q`).
