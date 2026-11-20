"""webhook: fully YAML-driven HTTP call (settings: url, method, headers, body_template)."""

from typing import Any

from alerting_contracts.config import ActionConfig

from plugins.actions.base import ActionPlugin, ActionResult, render_template, render_url
from plugins.actions.registry import register_action_plugin


def _looks_like_json(text: str) -> bool:
    return text.lstrip().startswith(("{", "["))


async def call_webhook(
    plugin: ActionPlugin,
    params: dict[str, str],
    config: ActionConfig,
    settings: dict[str, Any],
) -> ActionResult:
    """Shared by webhook-like plugins. ``settings`` must contain ``url``."""
    url = render_url(str(settings["url"]), params)
    method = str(settings.get("method", "POST")).upper()
    headers = {str(k): str(v) for k, v in (settings.get("headers") or {}).items()}
    template = settings.get("body_template")
    body: str | None = None
    if template is not None:
        template = str(template)
        is_json = _looks_like_json(template)
        body = render_template(template, params, json_escape=is_json)
        if is_json and not any(k.lower() == "content-type" for k in headers):
            headers["Content-Type"] = "application/json"
    return await plugin.send(method, url, config, headers=headers, content=body)


@register_action_plugin
class WebhookAction(ActionPlugin):
    type = "webhook"

    async def _run(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        if not config.settings.get("url"):
            return ActionResult(is_success=False, detail="webhook settings.url is not configured")
        return await call_webhook(self, params, config, config.settings)


__all__ = ["WebhookAction", "call_webhook"]
