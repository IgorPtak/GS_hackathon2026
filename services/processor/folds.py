"""Coalesced count flushes: folded events reach `alerts.count` and the UI at most once per second.

Counts live in Redis (`dedup-count:*`, INCRBY per batch) so every processor replica adds to the
same counter; the flusher GETDELs it, so a delta is applied exactly once whichever replica
flushes. Last-seen and last-event are tracked in memory and applied with the delta.

A replica killed between INCRBY and its flush leaves a counter nobody tracks. `adopt_orphans`
picks up counters not written for ORPHAN_IDLE_SECONDS (a live tracker flushes every second) from
`dedup-count-index` and maps them back to the latest alert of their rule + fingerprint; the
normal flush then applies them.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
from alerting_contracts.sse import AlertUpdatedEvent
from alerting_core.dedup import find_idle_fold_counters, return_fold_counts, take_fold_counts
from alerting_core.logging import get_logger
from alerting_core.publishing import publish_team_event
from alerting_core.storage.alerts_write import FoldUpdate, apply_folds
from redis.asyncio import Redis

log = get_logger(__name__)

ORPHAN_IDLE_SECONDS = 10
ORPHAN_SWEEP_SECONDS = 30.0
_COUNT_PREFIX = "dedup-count:"
# Latest alert per (rule, fingerprint): folds belong to it even if it was resolved meanwhile.
_LATEST_ALERTS = """
    SELECT DISTINCT ON (a.rule_id, a.fingerprint)
           a.rule_id, a.fingerprint, a.id::text AS id, a.last_seen, a.last_event
    FROM alerts a
    JOIN unnest($1::text[], $2::text[]) AS k(rule_id, fingerprint)
      ON a.rule_id = k.rule_id AND a.fingerprint = k.fingerprint
    ORDER BY a.rule_id, a.fingerprint, a.first_seen DESC
"""


@dataclass(slots=True)
class _PendingFold:
    count_key: str
    last_seen: datetime
    last_event: dict[str, Any]


class FoldTracker:
    """Remembers which alerts received folds since the last flush in this process."""

    def __init__(self, pool: asyncpg.Pool, redis: Redis) -> None:
        self._pool = pool
        self._redis = redis
        self._pending: dict[str, _PendingFold] = {}

    def add(
        self, alert_id: str, count_key: str, last_seen: datetime, last_event: dict[str, Any]
    ) -> None:
        current = self._pending.get(alert_id)
        if current is None or last_seen >= current.last_seen:
            self._pending[alert_id] = _PendingFold(count_key, last_seen, last_event)

    async def flush(self) -> int:
        """Apply pending deltas; returns how many alerts were updated.

        On any failure the pending entries go back into the tracker and taken deltas go back to
        Redis, so the next flush retries them; nothing is dropped while this process lives.
        """
        if not self._pending:
            return 0
        pending, self._pending = self._pending, {}
        taken: list[tuple[str, int]] = []
        try:
            alert_ids = list(pending)
            deltas = await take_fold_counts(self._redis, [pending[a].count_key for a in alert_ids])
            taken = [
                (pending[a].count_key, d) for a, d in zip(alert_ids, deltas, strict=True) if d > 0
            ]
            updates = [
                FoldUpdate(a, d, pending[a].last_seen, pending[a].last_event)
                for a, d in zip(alert_ids, deltas, strict=True)
                if d > 0
            ]
            async with self._pool.acquire() as connection:
                alerts = await apply_folds(connection, updates)
        except BaseException:
            self._restore(pending)
            if taken:
                await self._give_back(taken)
            raise
        updated = {alert.id for alert in alerts}
        lost = [
            (pending[u.alert_id].count_key, u.delta) for u in updates if u.alert_id not in updated
        ]
        if lost:
            # Alert row gone (deleted by hand): keep the counts for a later alert of the same key.
            await self._give_back(lost)
        now = datetime.now(UTC)
        await asyncio.gather(
            *(
                publish_team_event(self._redis, alert.team, AlertUpdatedEvent(at=now, alert=alert))
                for alert in alerts
            )
        )
        return len(alerts)

    async def adopt_orphans(self) -> int:
        """Track counters no live tracker flushes; returns how many were adopted."""
        tracked = {fold.count_key for fold in self._pending.values()}
        idle = await find_idle_fold_counters(self._redis, ORPHAN_IDLE_SECONDS * 1000)
        orphans = [
            key
            for key in idle
            if key not in tracked and key.count(":") >= 2  # dedup-count:<rule>:<fingerprint>
        ]
        if not orphans:
            return 0
        # rule ids never contain ':'; fingerprints are hex, so the last ':' splits the two.
        pairs = [key.removeprefix(_COUNT_PREFIX).rsplit(":", 1) for key in orphans]
        rows = await self._pool.fetch(
            _LATEST_ALERTS, [rule for rule, _ in pairs], [fingerprint for _, fingerprint in pairs]
        )
        by_pair = {(row["rule_id"], row["fingerprint"]): row for row in rows}
        adopted = 0
        for key, (rule_id, fingerprint) in zip(orphans, pairs, strict=True):
            row = by_pair.get((rule_id, fingerprint))
            if row is None:
                continue  # no alert committed for it: the counter expires with its grace TTL
            last_event = row["last_event"]
            if isinstance(last_event, str):
                last_event = json.loads(last_event)
            self.add(row["id"], key, row["last_seen"], last_event)
            adopted += 1
        if adopted:
            log.warning("fold_orphans_adopted", extra={"count": adopted})
        return adopted

    async def run_orphan_sweeper(
        self, stop: asyncio.Event, interval_seconds: float = ORPHAN_SWEEP_SECONDS
    ) -> None:
        """Adopt orphaned counters every interval; errors are logged and retried next tick."""
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                pass
            if stop.is_set():
                break  # the final flush already ran; adopted entries would never be applied
            try:
                await self.adopt_orphans()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("fold_orphan_sweep_failed")

    def _restore(self, pending: dict[str, _PendingFold]) -> None:
        for alert_id, fold in pending.items():
            self.add(alert_id, fold.count_key, fold.last_seen, fold.last_event)

    async def _give_back(self, deltas: list[tuple[str, int]]) -> None:
        try:
            await return_fold_counts(self._redis, deltas)
        except Exception:
            # Redis is down: these counts are lost (bounded by one flush interval of folds).
            log.exception("fold_counts_return_failed", extra={"keys": len(deltas)})

    async def run(self, stop: asyncio.Event, interval_seconds: float = 1.0) -> None:
        """Flush every interval until stopped, then once more so no count is left behind."""
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except TimeoutError:
                pass
            try:
                await self.flush()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("fold_flush_failed")
