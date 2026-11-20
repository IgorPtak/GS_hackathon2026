"""Processor side of auto-resolve (A-18): resolution events resolve matching open alerts."""

import asyncpg
from alerting_core.auto_resolve import ResolutionSignal, resolve_on_signals
from alerting_core.config.registry import ConfigRegistry
from alerting_core.logging import get_logger
from redis.asyncio import Redis

from .batch import ResolutionHook
from .evaluation import EventOutcome

log = get_logger(__name__)


def make_resolution_hook(
    pool: asyncpg.Pool, redis: Redis, registry: ConfigRegistry
) -> ResolutionHook:
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
