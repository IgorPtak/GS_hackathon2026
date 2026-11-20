"""Auto-resolve: close alerts when the source says the problem is gone, or after a silence.

Two paths, both resolving through `storage.transitions.resolve_alert` as `system:processor`:

- `resolve_on_signals`: the processor turns each resolution event into a `ResolutionSignal`.
  Matching is by `fingerprint` only, so a rule with a custom `dedup.fingerprint` (a different
  fingerprint than the schema profile's) is never matched by a resolution event; use
  `after_silence` for those rules.
- `push_silence_deadlines` / `resolve_silent_alerts`: the `silence-deadlines` sorted set holds
  the moment each alert goes quiet. Replicas claim due ids with one Lua script (ZRANGEBYSCORE +
  ZREM), so exactly one replica handles each id.

Events are published after commit; a publish failure never undoes a resolution.
"""

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
from alerting_contracts.alerts import Alert, AlertStatus, AuditEntry, ResolutionReason
from alerting_contracts.common import Actor
from alerting_contracts.config import Rule
from redis.asyncio import Redis

from .dedup import release_dedup_key
from .durations import parse_duration_ms
from .logging import get_logger
from .publishing import publish_alert_change
from .storage.rows import ALERT_SELECT, alert_from_row
from .storage.transitions import AlertNotFoundError, InvalidTransitionError, resolve_alert

log = get_logger(__name__)

SILENCE_DEADLINES_KEY = "silence-deadlines"
SYSTEM_ACTOR = Actor(id="system:processor")

# Atomic claim: only the replica whose script run removes a member gets it.
_CLAIM_SCRIPT = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
for _, member in ipairs(due) do
    redis.call('ZREM', KEYS[1], member)
end
return due
"""


@dataclass(frozen=True, slots=True)
class ResolutionSignal:
    """One resolution event: the source says the problem with this fingerprint is gone."""

    fingerprint: str
    source_id: str
    received_at: datetime


async def _resolve_and_publish(
    pool: asyncpg.Pool, redis: Redis, alert_id: str, reason: ResolutionReason
) -> Alert | None:
    """Resolve in its own transaction, then publish and release the dedup key.

    Returns None when the alert was already resolved (a human or another replica won).
    """
    async with pool.acquire() as connection:
        try:
            alert, audit = await resolve_alert(connection, alert_id, SYSTEM_ACTOR, reason)
        except (InvalidTransitionError, AlertNotFoundError):
            return None
    await _after_commit(redis, alert, audit, reason)
    return alert


async def _after_commit(
    redis: Redis, alert: Alert, audit: AuditEntry, reason: ResolutionReason
) -> None:
    await publish_alert_change(redis, alert, [audit])
    await release_dedup_key(redis, alert.rule_id, alert.fingerprint)
    log.info(
        "alert_auto_resolved",
        extra={"alert_id": alert.id, "rule_id": alert.rule_id, "reason": reason.value},
    )


async def resolve_on_signals(
    pool: asyncpg.Pool,
    redis: Redis,
    signals: Sequence[ResolutionSignal],
    rules: Mapping[str, Rule],
) -> list[Alert]:
    """Resolve open/acknowledged alerts matching the signals' fingerprints; returns those closed."""
    if not signals:
        return []
    latest: dict[str, datetime] = {}
    for signal in signals:
        known = latest.get(signal.fingerprint)
        if known is None or signal.received_at > known:
            latest[signal.fingerprint] = signal.received_at
    records = await pool.fetch(
        f"SELECT {ALERT_SELECT} FROM alerts WHERE fingerprint = ANY($1::text[]) "
        "AND status <> 'resolved'",
        list(latest),
    )
    resolved: list[Alert] = []
    for record in records:
        alert = alert_from_row(record)
        rule = rules.get(alert.rule_id)
        if rule is None or not rule.auto_resolve.on_resolution_event:
            continue
        if alert.first_seen > latest[alert.fingerprint]:
            continue  # stale resolution: the alert started after the source said "resolved"
        closed = await _resolve_and_publish(pool, redis, alert.id, ResolutionReason.source_resolved)
        if closed is not None:
            resolved.append(closed)
    return resolved


async def push_silence_deadlines(redis: Redis, items: Sequence[tuple[str, int]]) -> None:
    """ZADD (alert_id, deadline_ms); GT so a late, older event never moves a deadline back."""
    if not items:
        return
    await redis.zadd(SILENCE_DEADLINES_KEY, dict(items), gt=True)


async def _claim_due(redis: Redis, now_ms: int, batch: int) -> list[str]:
    claimed = await redis.eval(_CLAIM_SCRIPT, 1, SILENCE_DEADLINES_KEY, now_ms, batch)  # type: ignore[misc]
    return [member.decode() if isinstance(member, bytes) else str(member) for member in claimed]


async def resolve_silent_alerts(
    pool: asyncpg.Pool,
    redis: Redis,
    rules: Mapping[str, Rule],
    now_ms: int,
    batch: int = 200,
) -> list[Alert]:
    """Claim due deadlines and resolve alerts that stayed silent; returns those closed."""
    resolved: list[Alert] = []
    for alert_id in await _claim_due(redis, now_ms, batch):
        record = await pool.fetchrow(
            f"SELECT {ALERT_SELECT} FROM alerts WHERE id = $1::uuid", alert_id
        )
        if record is None:
            continue
        alert = alert_from_row(record)
        rule = rules.get(alert.rule_id)
        if alert.status is AlertStatus.resolved or rule is None:
            continue
        if rule.auto_resolve.after_silence is None:
            continue
        silence_ms = parse_duration_ms(rule.auto_resolve.after_silence)
        due_ms = int(alert.last_seen.timestamp() * 1000) + silence_ms
        if due_ms > now_ms:
            # Events arrived after the deadline was written; wait for the new one.
            await push_silence_deadlines(redis, [(alert_id, due_ms)])
            continue
        closed = await _resolve_and_publish(pool, redis, alert_id, ResolutionReason.silence)
        if closed is not None:
            resolved.append(closed)
    return resolved


async def run_silence_resolver(
    pool: asyncpg.Pool,
    redis: Redis,
    rules_provider: Callable[[], Mapping[str, Rule]],
    stop: asyncio.Event,
    interval_seconds: float = 1.0,
) -> None:
    """Resolve silent alerts every interval until `stop` is set; survives any per-pass error."""
    while not stop.is_set():
        try:
            now_ms = int(datetime.now(UTC).timestamp() * 1000)
            await resolve_silent_alerts(pool, redis, rules_provider(), now_ms)
        except asyncio.CancelledError:
            raise
        except Exception:  # background loop must outlive any one failure
            log.exception("silence_resolver_failed", extra={"alert_id": None, "rule_id": None})
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except TimeoutError:
            pass
