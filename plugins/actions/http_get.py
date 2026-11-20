"""http_get: GET params.url; success on 2xx."""

from alerting_contracts.config import ActionConfig

from plugins.actions.base import ActionPlugin, ActionResult
from plugins.actions.registry import register_action_plugin


@register_action_plugin
class HttpGetAction(ActionPlugin):
    type = "http_get"

    async def _run(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        url = params.get("url", "")
        if not url:
            return ActionResult(is_success=False, detail="missing required params: url")
        return await self.send("GET", url, config)
