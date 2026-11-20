"""Silence deadlines for alerts whose rule has `auto_resolve.after_silence` (A-18)."""

from collections.abc import Iterable

from alerting_contracts.config import Rule
from alerting_core.auto_resolve import push_silence_deadlines
from alerting_core.durations import parse_duration_ms
from redis.asyncio import Redis

# The silence resolver compares with `last_seen` in Postgres, which folds update up to ~1 s
# late (FoldTracker); the margin keeps a just-folded alert from resolving early.
SILENCE_MARGIN_MS = 2_000


def silence_deadlines(alerts: Iterable[tuple[str, Rule]], now_ms: int) -> list[tuple[str, int]]:
    """(alert_id, deadline_ms) for every alert whose rule resolves after silence."""
    items = []
    for alert_id, rule in alerts:
        silence = rule.auto_resolve.after_silence if rule.auto_resolve else None
        if silence:
            items.append((alert_id, now_ms + parse_duration_ms(silence) + SILENCE_MARGIN_MS))
    return items


async def push_alert_silences(
    redis: Redis, alerts: Iterable[tuple[str, Rule]], now_ms: int
) -> None:
    await push_silence_deadlines(redis, silence_deadlines(alerts, now_ms))
