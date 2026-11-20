"""Action plugins. Importing this package registers the built-ins."""

from plugins.actions import (  # noqa: F401
    escalate,
    http_get,
    open_ticket,
    restart_service,
    retry_workflow,
    webhook,
)
from plugins.actions.base import ActionPlugin, ActionResult
from plugins.actions.registry import (
    UnknownActionTypeError,
    get_action_plugin,
    register_action_plugin,
    registered_types,
)

__all__ = [
    "ActionPlugin",
    "ActionResult",
    "UnknownActionTypeError",
    "get_action_plugin",
    "register_action_plugin",
    "registered_types",
]
