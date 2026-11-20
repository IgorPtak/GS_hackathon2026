"""Processor side of auto-resolve (A-18): resolution events resolve matching open alerts."""

from collections.abc import Awaitable, Callable
from datetime import datetime

import asyncpg
from alerting_core.auto_resolve import ResolutionSignal, resolve_on_signals
from alerting_core.config.registry import ConfigRegistry
from alerting_core.logging import get_logger
from redis.asyncio import Redis

from .evaluation import EventOutcome

log = get_logger(__name__)


def current_resolutions(outcomes: list[EventOutcome]) -> list[EventOutcome]:
    """Resolution events not overtaken by a later firing event of the same fingerprint."""
    last_firing: dict[str, datetime] = {}
    for outcome in outcomes:
        if not outcome.normalized.is_resolution:
            fingerprint = outcome.normalized.fingerprint
            seen = last_firing.get(fingerprint)
            if seen is None or outcome.envelope.received_at > seen:
                last_firing[fingerprint] = outcome.envelope.received_at
    return [
        o
        for o in outcomes
        if o.normalized.is_resolution
        and o.envelope.received_at
        >= last_firing.get(o.normalized.fingerprint, o.envelope.received_at)
    ]


def make_resolution_hook(
    pool: asyncpg.Pool, redis: Redis, registry: ConfigRegistry
) -> Callable[[list[EventOutcome]], Awaitable[None]]:
    """Hook that resolves open alerts whose source sent a resolution event."""

    async def resolve(outcomes: list[EventOutcome]) -> None:
        signals = [
            ResolutionSignal(
                fingerprint=o.normalized.fingerprint,
                source_id=o.envelope.source_id,
                received_at=o.envelope.received_at,
            )
            for o in outcomes
        ]
        resolved = await resolve_on_signals(pool, redis, signals, registry.snapshot.of_kind("rule"))
        if resolved:
            log.info("alerts_auto_resolved", extra={"count": len(resolved)})

    return resolve
