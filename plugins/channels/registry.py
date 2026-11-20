"""Registry mapping `ChannelType` to its channel plugin."""

from alerting_contracts.config import ChannelType

from .base import ChannelPlugin

_PLUGINS: dict[ChannelType, ChannelPlugin] = {}


def register_channel_plugin(plugin: ChannelPlugin) -> None:
    """Register `plugin` under its `channel_type`; called once at import by each plugin file."""
    _PLUGINS[plugin.channel_type] = plugin


def get_channel_plugin(channel_type: ChannelType) -> ChannelPlugin | None:
    """Return the plugin for a channel type, or None when none is registered."""
    return _PLUGINS.get(channel_type)
