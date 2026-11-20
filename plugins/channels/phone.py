"""`phone` channel: mock phone call through the gateway, shown in the phone simulator."""

from alerting_contracts.config import ChannelType

from ._gateway import GatewayChannel
from .registry import register_channel_plugin


class PhoneChannel(GatewayChannel):
    """Calls `recipient.contacts.phone`; the text is what the mock call "says"."""

    channel_type = ChannelType.phone
    text_prefix = "Call: "


register_channel_plugin(PhoneChannel())
