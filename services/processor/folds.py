"""Coalesced count flushes: folded events reach `alerts.count` and the UI at most once per second.

Counts live in Redis (`dedup-count:*`, INCRBY per batch) so every processor replica adds to the
same counter; the flusher GETDELs it, so a delta is applied exactly once whichever replica
flushes. Last-seen and last-event are tracked in memory and applied with the delta.
"""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import asyncpg
from alerting_contracts.sse import AlertUpdatedEvent
from alerting_core.dedup import return_fold_counts, take_fold_counts
from alerting_core.logging import get_logger
from alerting_core.publishing import publish_team_event
from alerting_core.storage.alerts_write import FoldUpdate, apply_folds
from redis.asyncio import Redis

log = get_logger(__name__)


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
        """Apply pending deltas; returns how many alerts were updated."""
        if not self._pending:
            return 0
        pending, self._pending = self._pending, {}
        alert_ids = list(pending)
        deltas = await take_fold_counts(self._redis, [pending[a].count_key for a in alert_ids])
        updates = [
            FoldUpdate(alert_id, delta, pending[alert_id].last_seen, pending[alert_id].last_event)
            for alert_id, delta in zip(alert_ids, deltas, strict=True)
            if delta > 0
        ]
        try:
            async with self._pool.acquire() as connection:
                alerts = await apply_folds(connection, updates)
        except Exception:
            # Put the taken deltas back so the next flush (here or on a replica) applies them.
            await return_fold_counts(
                self._redis, [(pending[u.alert_id].count_key, u.delta) for u in updates]
            )
            for alert_id, fold in pending.items():
                self.add(alert_id, fold.count_key, fold.last_seen, fold.last_event)
            raise
        updated = {alert.id for alert in alerts}
        lost = [
            (pending[u.alert_id].count_key, u.delta) for u in updates if u.alert_id not in updated
        ]
        if lost:
            # Alert row gone (deleted by hand): keep the counts for a later alert of the same key.
            await return_fold_counts(self._redis, lost)
        now = datetime.now(UTC)
        for alert in alerts:
            await publish_team_event(
                self._redis, alert.team, AlertUpdatedEvent(at=now, alert=alert)
            )
        return len(alerts)

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
