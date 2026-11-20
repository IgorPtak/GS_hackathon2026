"""Shared transport for the `sms` and `phone` channels (mock gateway + phone simulator feed)."""

import logging
import uuid
from datetime import UTC, datetime
from typing import Literal

import httpx
from alerting_contracts.alerts import DeliveryJob, DeliveryPurpose
from alerting_contracts.api import PhoneMessage
from alerting_contracts.config import ChannelConfig, ChannelType, Recipient
from alerting_contracts.sse import PhoneMessageEvent
from redis.exceptions import RedisError

from .base import (
    ChannelContext,
    ChannelPlugin,
    ChannelRejectedError,
    ChannelUnavailableError,
)

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 5.0
MAX_RUNBOOK_STEPS = 3


def build_text(job: DeliveryJob, config: ChannelConfig, prefix: str = "") -> str:
    """`[SEVERITY] title`, link/steps per `runbook_presentation`, then the approval reply hint."""
    content = job.content
    lines = [f"{prefix}[{content.severity.value.upper()}] {content.title}"]
    if config.runbook_presentation != "none":
        lines.append(content.alert_url)
    if config.runbook_presentation == "full":
        steps = content.runbook_steps[:MAX_RUNBOOK_STEPS]
        lines += [f"{number}. {step}" for number, step in enumerate(steps, 1)]
    if job.purpose == DeliveryPurpose.approval_request and content.approval_code:
        code = content.approval_code
        lines.append(f"Reply APPROVE {code} or REJECT {code}")
    return "\n".join(lines)


class GatewayChannel(ChannelPlugin):
    """Posts to the mock gateway, then records the message for the phone simulator."""

    channel_type: Literal[ChannelType.sms, ChannelType.phone]
    text_prefix = ""

    async def send(
        self,
        job: DeliveryJob,
        recipient: Recipient | None,
        config: ChannelConfig,
        context: ChannelContext,
    ) -> None:
        address = getattr(recipient.contacts, self.channel_type.value, None) if recipient else None
        if recipient is None or not address:
            raise ChannelRejectedError(f"recipient has no {self.channel_type.value} contact")
        text = build_text(job, config, self.text_prefix)
        url = config.settings.get("gateway_url") or (
            f"{context.settings.mock_gateway_url}/{self.channel_type.value}"
        )
        await self._post(url, address, text, job, context)
        message = PhoneMessage(
            id=str(uuid.uuid4()),
            recipient_id=recipient.id,
            channel_type=self.channel_type,
            to=address,
            text=text,
            alert_id=job.alert_id,
            delivery_id=job.delivery_id,
            approval_code=job.content.approval_code,
            at=datetime.now(UTC),
        )
        if await self._store(message, context):
            await self._publish(message, context)

    async def _post(
        self, url: str, address: str, text: str, job: DeliveryJob, context: ChannelContext
    ) -> None:
        body = {"to": address, "text": text, "delivery_id": str(job.delivery_id)}
        try:
            response = await context.http.post(url, json=body, timeout=TIMEOUT_SECONDS)
        except httpx.HTTPError as error:  # timeout, connection refused
            raise ChannelUnavailableError(f"gateway unreachable: {error!r}") from error
        if response.status_code >= 500:
            raise ChannelUnavailableError(f"gateway http {response.status_code}")
        if response.status_code >= 400:
            raise ChannelRejectedError(f"gateway http {response.status_code}")

    async def _store(self, message: PhoneMessage, context: ChannelContext) -> bool:
        """Insert once per delivery; False when a redelivery already stored it."""
        if context.database is None:
            logger.warning(
                "phone_messages insert skipped: no database", extra={"event": "phone_store_skipped"}
            )
            return True
        try:
            inserted = await context.database.fetchval(
                'INSERT INTO phone_messages (id, recipient_id, channel_type, "to", text, alert_id,'
                " delivery_id, approval_code, at) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)"
                " ON CONFLICT (delivery_id) DO NOTHING RETURNING 1",
                uuid.UUID(message.id),
                message.recipient_id,
                message.channel_type.value,
                message.to,
                message.text,
                uuid.UUID(message.alert_id),
                message.delivery_id,
                message.approval_code,
                message.at,
            )
        except OSError as error:
            raise ChannelUnavailableError(f"database unavailable: {error}") from error
        return inserted is not None

    async def _publish(self, message: PhoneMessage, context: ChannelContext) -> None:
        event = PhoneMessageEvent(at=message.at, message=message)
        try:
            await context.redis.publish("broadcast", event.model_dump_json())
        except RedisError as error:
            raise ChannelUnavailableError(f"redis publish failed: {error}") from error
