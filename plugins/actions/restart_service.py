"""restart_service: POST settings.url, or {MOCK_GATEWAY_URL}/services/{service}/restart."""

import json
from urllib.parse import quote

from alerting_contracts.config import ActionConfig

from plugins.actions.base import ActionPlugin, ActionResult, mock_gateway_url
from plugins.actions.registry import register_action_plugin
from plugins.actions.webhook import call_webhook


@register_action_plugin
class RestartServiceAction(ActionPlugin):
    type = "restart_service"

    async def _run(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        if config.settings.get("url"):
            return await call_webhook(self, params, config, config.settings)
        service = params.get("service") or str(config.settings.get("service", ""))
        if not service:
            return ActionResult(
                is_success=False, detail="no service: set params.service or settings"
            )
        url = f"{mock_gateway_url()}/services/{quote(service, safe='')}/restart"
        return await self.send(
            "POST",
            url,
            config,
            headers={"Content-Type": "application/json"},
            content=json.dumps(params),
        )
