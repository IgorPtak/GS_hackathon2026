"""escalate: webhook behaviour when settings.url exists, else POST to the mock gateway."""

import json

from alerting_contracts.config import ActionConfig

from plugins.actions.base import ActionPlugin, ActionResult, mock_gateway_url
from plugins.actions.registry import register_action_plugin
from plugins.actions.webhook import call_webhook


@register_action_plugin
class EscalateAction(ActionPlugin):
    type = "escalate"

    async def _run(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        if config.settings.get("url"):
            return await call_webhook(self, params, config, config.settings)
        return await self.send(
            "POST",
            f"{mock_gateway_url()}/webhooks/escalations",
            config,
            headers={"Content-Type": "application/json"},
            content=json.dumps(params),
        )
