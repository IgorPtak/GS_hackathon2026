"""Group windows in Redis: buffer matched events, then flush each window into one summary alert.

- `group-buffer:<rule>:<key>` collects GroupEvent JSON; the first event of a window adds
  `<rule>:<key>` to `group-deadlines` (NX) with score = now + window.
- The flusher claims due members with one Lua script: ZREM decides the single winner, which
  RENAMEs the buffer to `group-flushing:<rule>:<key>:<deadline>` and parks `retry:<that key>`
  in `group-deadlines` before returning. Events arriving after the rename open a new window.
- The summary alert id is derived from the flushing key and inserted with ON CONFLICT DO NOTHING,
  so a flusher that dies after the claim is replaced by the retry entry without a duplicate.
"""

import asyncio
import time
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime

import asyncpg
from alerting_contracts.alerts import DeliveryPurpose
from alerting_contracts.config import Rule
from alerting_contracts.sse import AlertCreatedEvent, AuditAppendedEvent
from alerting_core.config.registry import ConfigRegistry
from alerting_core.durations import parse_duration_ms
from alerting_core.grouping import (
    GroupEvent,
    group_alert_id,
    group_member,
    split_group_member,
    summarize_group,
)
from alerting_core.logging import get_logger
from alerting_core.metrics import ALERTS_CREATED
from alerting_core.outbox import enqueue_outbox_rows
from alerting_core.publishing import publish_team_event
from alerting_core.settings import Settings
from alerting_core.storage.alerts_write import insert_alerts, insert_audit_entries
from pydantic import ValidationError
from redis.asyncio import Redis

from .deliveries import build_side_effects, throttle_targets
from .silences import push_alert_silences

log = get_logger(__name__)

DEADLINES_KEY = "group-deadlines"
_GRACE_MS = 60_000
# A claimed window not finished within this time is re-flushed by any processor.
RETRY_AFTER_MS = 30_000

_CLAIM_DUE = """
local due = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'WITHSCORES', 'LIMIT', 0, ARGV[2])
local claimed = {}
for i = 1, #due, 2 do
  local member, score = due[i], due[i + 1]
  if redis.call('ZREM', KEYS[1], member) == 1 then
    local flushing = nil
    if string.sub(member, 1, 6) == 'retry:' then
      flushing = string.sub(member, 7)
    else
      local buffer = 'group-buffer:' .. member
      local target = 'group-flushing:' .. member .. ':' .. score
      if redis.call('EXISTS', buffer) == 1 and redis.call('EXISTS', target) == 0 then
        flushing = target
        redis.call('RENAME', buffer, flushing)
      end
    end
    if flushing and redis.call('EXISTS', flushing) == 1 then
      -- Every claim extends the TTL, so a window survives an outage of any length.
      redis.call('PEXPIRE', flushing, tonumber(ARGV[4]))
      redis.call('ZADD', KEYS[1], tonumber(ARGV[1]) + tonumber(ARGV[3]), 'retry:' .. flushing)
      table.insert(claimed, flushing)
    elseif flushing then
      table.insert(claimed, 'expired:' .. flushing)
    end
  end
end
return claimed
"""


@dataclass(frozen=True, slots=True)
class BufferedEvent:
    rule: Rule
    key: str
    event: GroupEvent


async def buffer_group_events(redis: Redis, items: Sequence[BufferedEvent], now_ms: int) -> None:
    """Append events to their windows; the first event of a window schedules its flush."""
    if not items:
        return
    async with redis.pipeline(transaction=True) as pipeline:
        for item in items:
            if item.rule.group is None:
                continue
            window_ms = parse_duration_ms(item.rule.group.window)
            member = group_member(item.rule.id, item.key)
            buffer = f"group-buffer:{member}"
            pipeline.rpush(buffer, item.event.model_dump_json())
            pipeline.pexpire(buffer, window_ms + _GRACE_MS)
            pipeline.zadd(DEADLINES_KEY, {member: now_ms + window_ms}, nx=True)
        await pipeline.execute()


def parse_flushing_key(flushing: str) -> tuple[str, str, int]:
    """(rule_id, group_key, deadline_ms) of `group-flushing:<rule>:<key>:<deadline>`."""
    member, _, deadline = flushing.removeprefix("group-flushing:").rpartition(":")
    rule_id, key = split_group_member(member)
    return rule_id, key, int(float(deadline))


def _parse_events(raw_events: list[bytes], rule_id: str, key: str) -> list[GroupEvent]:
    """Valid events of a window; a corrupt entry is logged and skipped, not the whole window."""
    events = []
    for raw in raw_events:
        try:
            events.append(GroupEvent.model_validate_json(raw))
        except ValidationError:
            log.warning("group_event_invalid", extra={"rule_id": rule_id, "group_key": key})
    return events


class GroupFlusher:
    """Claims due windows and writes their summary alerts (any number of replicas)."""

    def __init__(
        self, pool: asyncpg.Pool, redis: Redis, registry: ConfigRegistry, settings: Settings
    ) -> None:
        self._pool = pool
        self._redis = redis
        self._registry = registry
        self._settings = settings
        self._claim = redis.register_script(_CLAIM_DUE)

    async def flush_due(self, now_ms: int | None = None, limit: int = 100) -> int:
        """Flush every window due at `now_ms`; returns how many summaries were created."""
        now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        claimed = await self._claim(
            keys=[DEADLINES_KEY], args=[now_ms, limit, RETRY_AFTER_MS, RETRY_AFTER_MS + _GRACE_MS]
        )
        created = 0
        for raw in claimed:
            flushing = raw.decode() if isinstance(raw, bytes) else raw
            if flushing.startswith("expired:"):
                log.error("group_window_expired", extra={"flushing_key": flushing[8:]})
                continue
            created += await self._flush_window(flushing)
        return created

    async def _flush_window(self, flushing: str) -> int:
        rule_id, key, deadline_ms = parse_flushing_key(flushing)
        rule = self._registry.snapshot.of_kind("rule").get(rule_id)
        raw_events = await self._redis.lrange(flushing, 0, -1)
        if rule is None or rule.group is None or not raw_events:
            log.warning("group_window_dropped", extra={"rule_id": rule_id, "group_key": key})
            await self._finish(flushing)
            return 0
        events = _parse_events(raw_events, rule_id, key)
        if not events:
            await self._finish(flushing)
            return 0
        now = datetime.now(UTC)
        alert = summarize_group(rule, key, events, group_alert_id(flushing, deadline_ms), now)
        snapshot = self._registry.snapshot
        allowed, suppressed = await throttle_targets(
            self._redis, snapshot, rule, alert, events[-1].source, now
        )
        effects = build_side_effects(
            rule,
            alert,
            allowed,
            suppressed,
            public_base_url=self._settings.public_base_url,
            event_sent_at=events[0].sent_at or events[0].received_at,
            purpose=DeliveryPurpose.group_summary,
            snapshot=snapshot,
        )
        async with self._pool.acquire() as connection, connection.transaction():
            inserted = await insert_alerts(connection, [alert])
            audit = []
            if alert.id in inserted:
                await enqueue_outbox_rows(connection, effects.outbox_rows)
                audit = await insert_audit_entries(connection, effects.audit_rows)
        await self._finish(flushing)
        if alert.id not in inserted:
            return 0  # an earlier flush of this window committed it
        ALERTS_CREATED.inc()
        await push_alert_silences(self._redis, [(alert.id, rule)], int(time.time() * 1000))
        log.info(
            "group_summary_created",
            extra={"alert_id": alert.id, "rule_id": rule.id, "count": alert.count},
        )
        await publish_team_event(self._redis, alert.team, AlertCreatedEvent(at=now, alert=alert))
        for entry in audit:
            await publish_team_event(
                self._redis, alert.team, AuditAppendedEvent(at=now, entry=entry)
            )
        return 1

    async def _finish(self, flushing: str) -> None:
        async with self._redis.pipeline(transaction=True) as pipeline:
            pipeline.delete(flushing)
            pipeline.zrem(DEADLINES_KEY, f"retry:{flushing}")
            await pipeline.execute()

    async def run(self, stop: asyncio.Event, interval_seconds: float = 0.5) -> None:
        """Flush due windows until stopped; errors are logged and retried next tick."""
        while not stop.is_set():
            try:
                await self.flush_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Redis/Postgres down or a bug: claimed windows come back via their retry entry.
                log.exception("group_flush_failed")
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
