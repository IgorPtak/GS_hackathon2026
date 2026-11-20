"""retry_workflow: POST {settings.base_url}/{workflow_id}/retry."""

from urllib.parse import quote

from alerting_contracts.config import ActionConfig

from plugins.actions.base import ActionPlugin, ActionResult, mock_gateway_url
from plugins.actions.registry import register_action_plugin


@register_action_plugin
class RetryWorkflowAction(ActionPlugin):
    type = "retry_workflow"

    async def _run(self, params: dict[str, str], config: ActionConfig) -> ActionResult:
        workflow_id = params.get("workflow_id", "")
        if not workflow_id:
            return ActionResult(
                is_success=False, detail="missing required params: workflow_id"
            )
        base = str(
            config.settings.get("base_url") or f"{mock_gateway_url()}/workflows"
        ).rstrip("/")
        return await self.send(
            "POST", f"{base}/{quote(workflow_id, safe='')}/retry", config
        )
