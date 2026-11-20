"""Interface for channel plugins (ui, email, sms, phone, webhook)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlsplit

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


def classify_http_status(status: int) -> None:
    """Return for 2xx; raise the matching channel error otherwise.

    408 and 429 are transient so they retry; other 4xx and 3xx (we never follow redirects to
    unvetted hosts) are permanent; 5xx retries.
    """
    if 200 <= status < 300:
        return
    if status in (408, 429) or status >= 500:
        raise ChannelUnavailableError(f"http {status}")
    if 300 <= status < 400:
        raise ChannelRejectedError(f"unexpected redirect: http {status}")
    raise ChannelRejectedError(f"http {status}")


def check_host_allowed(url_or_host: str, context: "ChannelContext") -> None:
    """Raise `ChannelRejectedError` unless the host is in `settings.channel_allowed_hosts`."""
    host = urlsplit(url_or_host if "//" in url_or_host else f"//{url_or_host}").hostname
    if not host or host not in context.settings.channel_allowed_hosts:
        raise ChannelRejectedError(f"host {host!r} is not in channel_allowed_hosts")


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
