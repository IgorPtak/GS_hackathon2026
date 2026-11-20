"""Source plugins. Importing this package registers the built-in HTTP plugins."""

from . import alertmanager, webhook  # noqa: F401  (import registers the plugin)
from .base import HttpSourcePlugin
from .registry import get_source_plugin, register_source_plugin

__all__ = ["HttpSourcePlugin", "get_source_plugin", "register_source_plugin"]
