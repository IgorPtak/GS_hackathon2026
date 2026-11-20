"""`sms` channel: mock SMS through the gateway, shown in the phone simulator."""

from alerting_contracts.config import ChannelType

from ._gateway import GatewayChannel
from .registry import register_channel_plugin


class SmsChannel(GatewayChannel):
    """Sends to `recipient.contacts.sms`."""

    channel_type = ChannelType.sms


register_channel_plugin(SmsChannel())
