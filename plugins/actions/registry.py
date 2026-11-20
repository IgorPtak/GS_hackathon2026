"""Registry mapping action ``type`` to plugin class."""

from __future__ import annotations

from plugins.actions.base import ActionPlugin

_REGISTRY: dict[str, type[ActionPlugin]] = {}


class UnknownActionTypeError(KeyError):
    """No action plugin is registered under this type."""


def register_action_plugin[T: type[ActionPlugin]](cls: T) -> T:
    """Class decorator: register ``cls`` under ``cls.type``."""
    _REGISTRY[cls.type] = cls
    return cls


def get_action_plugin(type: str) -> ActionPlugin:
    try:
        return _REGISTRY[type]()
    except KeyError:
        raise UnknownActionTypeError(type) from None


def registered_types() -> list[str]:
    return sorted(_REGISTRY)


__all__: list[str] = [
    "UnknownActionTypeError",
    "get_action_plugin",
    "register_action_plugin",
    "registered_types",
]
