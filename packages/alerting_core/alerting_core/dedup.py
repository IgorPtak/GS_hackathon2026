"""Dedup of identical events (same rule + fingerprint) in Redis; see contracts/storage.md.

- `dedup:<rule_id>:<fingerprint>` holds the alert id, set with `SET NX PX <window>`. The id is
  generated before the SET, so whoever wins the SET owns that id and inserts the alert with
  `ON CONFLICT (id) DO NOTHING`; a redelivered event finds the key and can recreate an alert
  that a crash lost between SET and commit.
- `dedup-count:<rule_id>:<fingerprint>` counts folded events. Flushers take the counter with
  GETDEL and add the delta to `alerts.count`, so several processors can flush the same key
  without double counting; a delta whose alert is not committed yet is put back with INCRBY.
- `dedup-count-index` is a sorted set of those counters scored by their last write (ms). Orphan
  adoption reads it instead of SCANning the keyspace, whose cost grew with every replica and with
  the millions of `delivery-done:*` keys (A-41 load test: SCAN was the top Redis CPU consumer).
"""

import time
from collections.abc import Sequence
from dataclasses import dataclass

from redis.asyncio import Redis

# The counter outlives the window so a late flush still finds the folded events.
_COUNT_GRACE_MS = 60_000
DEDUP_COUNT_INDEX = "dedup-count-index"
# Candidates idle long enough that still exist; index entries of counters already taken (GETDEL)
# or expired are dropped in the same script, so a concurrent INCRBY + ZADD cannot be lost between
# an EXISTS check and the ZREM.
_IDLE_COUNTERS_SCRIPT = """
local candidates = redis.call('ZRANGEBYSCORE', KEYS[1], '-inf', ARGV[1], 'LIMIT', 0, ARGV[2])
local live = {}
for _, key in ipairs(candidates) do
  if redis.call('EXISTS', key) == 1 then
    table.insert(live, key)
  else
    redis.call('ZREM', KEYS[1], key)
  end
end
return live
"""


def dedup_key(rule_id: str, fingerprint: str) -> str:
    return f"dedup:{rule_id}:{fingerprint}"


def dedup_count_key(rule_id: str, fingerprint: str) -> str:
    return f"dedup-count:{rule_id}:{fingerprint}"


@dataclass(frozen=True, slots=True)
class DedupClaim:
    """One rule match asking for the alert of its dedup window."""

    rule_id: str
    fingerprint: str
    window_ms: int
    candidate_alert_id: str


@dataclass(frozen=True, slots=True)
class DedupResult:
    alert_id: str
    is_new: bool


async def claim_dedup_keys(redis: Redis, claims: Sequence[DedupClaim]) -> list[DedupResult]:
    """SET NX each key with its candidate id; returns the owning alert id per claim, in order.

    One pipeline per batch. Identical events inside the same batch resolve to the first claim's
    id because the pipeline runs in order.
    """
    if not claims:
        return []
    async with redis.pipeline(transaction=False) as pipeline:
        for claim in claims:
            key = dedup_key(claim.rule_id, claim.fingerprint)
            pipeline.set(key, claim.candidate_alert_id, nx=True, px=max(claim.window_ms, 1))
            pipeline.get(key)
        replies = await pipeline.execute()
    results = []
    for index, claim in enumerate(claims):
        was_set, owner = replies[2 * index], replies[2 * index + 1]
        # owner is None only if the key expired between SET and GET (window of a few ms).
        owner_id = owner.decode() if owner is not None else claim.candidate_alert_id
        results.append(DedupResult(alert_id=owner_id, is_new=bool(was_set)))
    return results


async def rearm_dedup_keys(redis: Redis, claims: Sequence[tuple[DedupClaim, str]]) -> None:
    """Point expired windows at the still-open alert (claim, open alert id), overwriting."""
    if not claims:
        return
    async with redis.pipeline(transaction=False) as pipeline:
        for claim, alert_id in claims:
            pipeline.set(
                dedup_key(claim.rule_id, claim.fingerprint), alert_id, px=max(claim.window_ms, 1)
            )
        await pipeline.execute()


async def record_folds(redis: Redis, folds: Sequence[tuple[DedupClaim, int]]) -> None:
    """Add `count` folded events per (claim, count)."""
    if not folds:
        return
    now_ms = _now_ms()
    async with redis.pipeline(transaction=False) as pipeline:
        for fold, count in folds:
            key = dedup_count_key(fold.rule_id, fold.fingerprint)
            pipeline.incrby(key, count)
            pipeline.pexpire(key, fold.window_ms + _COUNT_GRACE_MS)
            pipeline.zadd(DEDUP_COUNT_INDEX, {key: now_ms})
        await pipeline.execute()


async def take_fold_counts(redis: Redis, count_keys: Sequence[str]) -> list[int]:
    """Atomically take (GETDEL) the pending fold count of each key; 0 when none."""
    if not count_keys:
        return []
    async with redis.pipeline(transaction=False) as pipeline:
        for key in count_keys:
            pipeline.getdel(key)
        replies = await pipeline.execute()
    return [int(reply) if reply is not None else 0 for reply in replies]


async def return_fold_counts(redis: Redis, deltas: Sequence[tuple[str, int]]) -> None:
    """Put back deltas that could not be flushed yet (alert not committed by its owner)."""
    if not deltas:
        return
    now_ms = _now_ms()
    async with redis.pipeline(transaction=False) as pipeline:
        for key, delta in deltas:
            pipeline.incrby(key, delta)
            pipeline.pexpire(key, _COUNT_GRACE_MS * 5)
            pipeline.zadd(DEDUP_COUNT_INDEX, {key: now_ms})
        await pipeline.execute()


async def find_idle_fold_counters(redis: Redis, idle_ms: int, limit: int = 1000) -> list[str]:
    """Existing fold counters not written for `idle_ms`, oldest first (at most `limit`)."""
    keys = await redis.eval(_IDLE_COUNTERS_SCRIPT, 1, DEDUP_COUNT_INDEX, _now_ms() - idle_ms, limit)
    return [key.decode() if isinstance(key, bytes) else key for key in keys]


def _now_ms() -> int:
    return int(time.time() * 1000)


async def release_dedup_key(redis: Redis, rule_id: str, fingerprint: str) -> None:
    """Forget the window (e.g. after auto-resolve) so the next event opens a new alert."""
    await redis.delete(dedup_key(rule_id, fingerprint), dedup_count_key(rule_id, fingerprint))
