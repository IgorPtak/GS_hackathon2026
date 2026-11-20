"""open_ticket: POST {MOCK_GATEWAY_URL}/tickets (or settings.url) with the summary."""

import json

from alerting_contracts.config import ActionConfig

from plugins.actions.base import ActionPlugin, ActionResult, mock_gateway_url
from plugins.actions.registry import register_action_plugin
from plugins.actions.webhook import call_webhook


@register_action_plugin
class OpenTicketAction(ActionPlugin):
    type = "open_ticket"

    async def _run(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        if config.settings.get("body_template") and config.settings.get("url"):
            return await call_webhook(self, params, config, config.settings)
        summary = params.get("summary", "")
        if not summary:
            return ActionResult(is_success=False, detail="missing required params: summary")
        url = str(config.settings.get("url") or f"{mock_gateway_url()}/tickets")
        body = {
            "summary": summary,
            **{k: v for k, v in params.items() if k != "summary"},
        }
        return await self.send(
            "POST",
            url,
            config,
            headers={"Content-Type": "application/json"},
            content=json.dumps(body),
        )
