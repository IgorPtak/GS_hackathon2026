"""`ui` channel: publishes a `notification` SSE event to the team's pub/sub channel."""

from datetime import UTC, datetime

from alerting_contracts.alerts import DeliveryJob
from alerting_contracts.config import ChannelConfig, ChannelType, Recipient
from alerting_contracts.sse import NotificationEvent
from redis.exceptions import RedisError

from .base import ChannelContext, ChannelPlugin, ChannelUnavailableError
from .registry import register_channel_plugin


class UiChannel(ChannelPlugin):
    """Team-wide toast; the api service relays pub/sub messages to browsers over SSE."""

    channel_type = ChannelType.ui

    async def send(
        self,
        job: DeliveryJob,
        recipient: Recipient | None,
        config: ChannelConfig,
        context: ChannelContext,
    ) -> None:
        event = NotificationEvent(
            at=datetime.now(UTC),
            alert_id=job.alert_id,
            team=job.team,
            title=job.content.title,
            severity=job.content.severity,
            delivery_id=job.delivery_id,
        )
        try:
            await context.redis.publish(f"alerts.team.{job.team}", event.model_dump_json())
        except RedisError as error:
            raise ChannelUnavailableError(f"redis publish failed: {error}") from error


register_channel_plugin(UiChannel())
