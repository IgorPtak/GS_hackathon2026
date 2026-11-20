"""Auto-resolve: close alerts when the source says the problem is gone, or after a silence.

Two paths, both resolving through `storage.transitions.resolve_alert` as `system:processor`:

- `resolve_on_signals`: the processor turns each resolution event into a `ResolutionSignal`.
  Matching is by `fingerprint` only, so a rule with a custom `dedup.fingerprint` (a different
  fingerprint than the schema profile's) is never matched by a resolution event; use
  `after_silence` for those rules. A resolution that overtakes its firing event on another
  replica finds nothing to resolve; `after_silence` is the safety net for that too.
- `push_silence_deadlines` / `resolve_silent_alerts`: the `silence-deadlines` sorted set holds
  the moment each alert goes quiet. A replica claims due ids by leasing them (score moved
  CLAIM_LEASE_MS ahead in one Lua script), so exactly one replica handles each id and a crash
  or error mid-pass only delays it. Unflushed folds (`dedup-count:*`) keep an alert open.
  Deadlines live only in Redis: alerts open before a rule gained `after_silence`, or before a
  Redis flush, get one on their next event.

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

from .dedup import dedup_count_key, dedup_key
from .durations import parse_duration_ms
from .logging import get_logger
from .publishing import publish_alert_change
from .storage.rows import ALERT_SELECT, alert_from_row
from .storage.transitions import AlertNotFoundError, InvalidTransitionError, resolve_alert

log = get_logger(__name__)

SILENCE_DEADLINES_KEY = "silence-deadlines"
SYSTEM_ACTOR = Actor(id="system:processor")

# A claimed id that is neither resolved nor rescheduled comes back after this lease.
CLAIM_LEASE_MS = 30_000

# Atomic claim: moving the score past now hides the id from other replicas until the lease ends.
_CLAIM_SCRIPT = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
for _, member in ipairs(due) do
    redis.call('ZADD', KEYS[1], 'XX', tonumber(ARGV[1]) + tonumber(ARGV[3]), member)
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
    try:
        await _after_commit(redis, alert, audit)
    except Exception:  # committed: a lost publish or key release must not hide the resolution
        log.exception(
            "alert_auto_resolve_publish_failed",
            extra={"alert_id": alert.id, "rule_id": alert.rule_id},
        )
    log.info(
        "alert_auto_resolved",
        extra={"alert_id": alert.id, "rule_id": alert.rule_id, "reason": reason.value},
    )
    return alert


async def _after_commit(redis: Redis, alert: Alert, audit: AuditEntry) -> None:
    await publish_alert_change(redis, alert, [audit])
    # Only the window key: an unflushed fold count still belongs to (and lands on) this alert.
    await redis.delete(dedup_key(alert.rule_id, alert.fingerprint))


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
        if alert.last_seen > latest[alert.fingerprint]:
            continue  # stale resolution: the alert fired again after the source said "resolved"
        try:
            closed = await _resolve_and_publish(
                pool, redis, alert.id, ResolutionReason.source_resolved
            )
        except Exception:  # one failing alert must not keep the others open
            log.exception(
                "alert_auto_resolve_failed", extra={"alert_id": alert.id, "rule_id": alert.rule_id}
            )
            continue
        if closed is not None:
            resolved.append(closed)
    return resolved


async def push_silence_deadlines(redis: Redis, items: Sequence[tuple[str, int]]) -> None:
    """ZADD (alert_id, deadline_ms); GT so a late, older event never moves a deadline back."""
    if not items:
        return
    await redis.zadd(SILENCE_DEADLINES_KEY, dict(items), gt=True)


async def _claim_due(redis: Redis, now_ms: int, batch: int) -> list[str]:
    claimed = await redis.eval(  # type: ignore[misc]
        _CLAIM_SCRIPT, 1, SILENCE_DEADLINES_KEY, now_ms, batch, CLAIM_LEASE_MS
    )
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
        try:
            closed = await _handle_silence(pool, redis, rules, alert_id, now_ms)
        except Exception:  # the lease brings this id back; the rest of the pass goes on
            log.exception("silence_resolve_failed", extra={"alert_id": alert_id, "rule_id": None})
            continue
        if closed is not None:
            resolved.append(closed)
    return resolved


async def _handle_silence(
    pool: asyncpg.Pool, redis: Redis, rules: Mapping[str, Rule], alert_id: str, now_ms: int
) -> Alert | None:
    """Resolve, reschedule or drop one claimed id."""
    record = await pool.fetchrow(f"SELECT {ALERT_SELECT} FROM alerts WHERE id = $1::uuid", alert_id)
    alert = alert_from_row(record) if record is not None else None
    rule = rules.get(alert.rule_id) if alert is not None else None
    if (
        alert is None
        or alert.status is AlertStatus.resolved
        or rule is None
        or rule.auto_resolve.after_silence is None
    ):
        await redis.zrem(SILENCE_DEADLINES_KEY, alert_id)
        return None
    silence_ms = parse_duration_ms(rule.auto_resolve.after_silence)
    due_ms = int(alert.last_seen.timestamp() * 1000) + silence_ms
    if await _has_pending_folds(redis, alert):
        due_ms = max(due_ms, now_ms + silence_ms)  # events arrived that Postgres has not seen yet
    if due_ms > now_ms:
        await redis.zadd(SILENCE_DEADLINES_KEY, {alert_id: due_ms})
        return None
    closed = await _resolve_and_publish(pool, redis, alert_id, ResolutionReason.silence)
    await redis.zrem(SILENCE_DEADLINES_KEY, alert_id)
    return closed


async def _has_pending_folds(redis: Redis, alert: Alert) -> bool:
    pending = await redis.get(dedup_count_key(alert.rule_id, alert.fingerprint))
    return pending is not None and int(pending) > 0


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
