"""Registry mapping `SourceType` to its HTTP source plugin."""

from alerting_contracts.events import SourceType

from .base import HttpSourcePlugin

_PLUGINS: dict[SourceType, HttpSourcePlugin] = {}


def register_source_plugin(source_type: SourceType, plugin: HttpSourcePlugin) -> None:
    """Register `plugin` for `source_type`; called once at import by each plugin file."""
    _PLUGINS[source_type] = plugin


def get_source_plugin(source_type: SourceType) -> HttpSourcePlugin | None:
    """Return the HTTP plugin for a source type, or None (e.g. log_tail is not HTTP)."""
    return _PLUGINS.get(source_type)
