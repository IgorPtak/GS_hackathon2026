"""Interface for channel plugins (ui, email, sms, phone, webhook)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

import asyncpg
import httpx
from alerting_contracts.alerts import DeliveryJob
from alerting_contracts.config import ChannelConfig, ChannelType, Recipient
from alerting_core.settings import Settings
from redis.asyncio import Redis


class ChannelUnavailableError(Exception):
    """Retryable failure: timeout, 5xx, connection refused; the worker backs off."""


class ChannelRejectedError(Exception):
    """Permanent failure: bad address, 4xx. The delivery worker does not retry."""


@dataclass(frozen=True)
class ChannelContext:
    """Shared clients a plugin may use; owned and closed by the delivery worker."""

    redis: Redis
    http: httpx.AsyncClient
    settings: Settings
    database: asyncpg.Pool | None = None


class ChannelPlugin(ABC):
    """Sends one `DeliveryJob` through one channel type.

    Plugins only format and transport the already-rendered `job.content`; they never retry,
    write delivery status or choose fallbacks (the delivery worker does).
    """

    channel_type: ChannelType

    @abstractmethod
    async def send(
        self,
        job: DeliveryJob,
        recipient: Recipient | None,
        config: ChannelConfig,
        context: ChannelContext,
    ) -> None:
        """Deliver `job`; raise `ChannelUnavailableError` (retryable) or `ChannelRejectedError`."""
