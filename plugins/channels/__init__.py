"""Channel plugins. Importing this package registers the built-in channels."""

from . import email, phone, sms, ui, webhook  # noqa: F401  (import registers the plugins)
from .base import (
    ChannelContext,
    ChannelPlugin,
    ChannelRejectedError,
    ChannelUnavailableError,
)
from .registry import get_channel_plugin, register_channel_plugin

__all__ = [
    "ChannelContext",
    "ChannelPlugin",
    "ChannelRejectedError",
    "ChannelUnavailableError",
    "get_channel_plugin",
    "register_channel_plugin",
]
