"""In-memory typed configuration snapshots, reloaded when `config.changed` arrives.

A snapshot is immutable and replaced in one assignment, so readers never see a half-loaded state.
Reload re-reads every document from Postgres. A row that fails validation keeps that id's previous
model (or is dropped if new) while the rest still swaps. Reloads are serialized and coalesced, and
a periodic reconcile catches notifications lost to a Redis outage.
"""

import asyncio
import contextlib
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import asyncpg
from alerting_contracts.config import (
    ActionConfig,
    ChannelConfig,
    Recipient,
    Rule,
    SchemaProfile,
    SourceConfig,
    Team,
)
from pydantic import BaseModel
from redis.asyncio import Redis

from ..logging import get_logger
from .kinds import get_kind, registered_kinds
from .store import CONFIG_CHANGED_CHANNEL

log = get_logger(__name__)

_MAX_BACKOFF_SECONDS = 5.0


@dataclass(frozen=True)
class ConfigSnapshot:
    """All validated documents by kind, then id, plus the stored version of each."""

    documents: Mapping[str, Mapping[str, BaseModel]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    versions: Mapping[tuple[str, str], int] = field(default_factory=lambda: MappingProxyType({}))

    def of_kind(self, kind: str) -> Mapping[str, Any]:
        """Documents of one kind keyed by id (empty when none)."""
        return self.documents.get(kind, MappingProxyType({}))


class ConfigRegistry:
    """Holds the current ConfigSnapshot and keeps it fresh.

    Workers call `await registry.start(pool, redis)` once and read `registry.snapshot` or the
    typed accessors on every event; `on_reload` callbacks (e.g. recompile regexes) run after
    each successful swap with the new snapshot.
    """

    def __init__(
        self,
        reconcile_interval: float = 30.0,
        initial_load_timeout: float = 30.0,
    ) -> None:
        self._snapshot = ConfigSnapshot()
        self._pool: asyncpg.Pool | None = None
        self._tasks: list[asyncio.Task[None]] = []
        self._pending: set[asyncio.Task[bool]] = set()
        self._subscribed = asyncio.Event()
        self._lock = asyncio.Lock()
        self._is_dirty = False
        self._last_reload_ok = False
        self._fingerprint: tuple[Any, int] | None = None
        self._reconcile_interval = reconcile_interval
        self._initial_load_timeout = initial_load_timeout
        self.on_reload: list[Callable[[ConfigSnapshot], None]] = []

    @property
    def snapshot(self) -> ConfigSnapshot:
        """The current immutable snapshot."""
        return self._snapshot

    def get(self, kind: str, document_id: str) -> Any | None:
        """One document or None."""
        return self._snapshot.of_kind(kind).get(document_id)

    def rules(self) -> Mapping[str, Rule]:
        return self._snapshot.of_kind("rule")

    def schema_profiles(self) -> Mapping[str, SchemaProfile]:
        return self._snapshot.of_kind("schema_profile")

    def sources(self) -> Mapping[str, SourceConfig]:
        return self._snapshot.of_kind("source")

    def recipients(self) -> Mapping[str, Recipient]:
        return self._snapshot.of_kind("recipient")

    def teams(self) -> Mapping[str, Team]:
        return self._snapshot.of_kind("team")

    def channels(self) -> Mapping[str, ChannelConfig]:
        return self._snapshot.of_kind("channel")

    def actions(self) -> Mapping[str, ActionConfig]:
        return self._snapshot.of_kind("action")

    async def reload(self) -> bool:
        """Re-read all documents and swap the snapshot; False if the old one was kept.

        Concurrent calls coalesce: a burst runs at most two reloads (one in flight plus one
        that covers everything requested meanwhile).
        """
        self._is_dirty = True
        async with self._lock:
            if not self._is_dirty:
                return self._last_reload_ok
            self._is_dirty = False
            self._last_reload_ok = await self._reload_once()
            return self._last_reload_ok

    async def _reload_once(self) -> bool:
        if self._pool is None:
            raise RuntimeError("ConfigRegistry.start() has not been called")
        try:
            rows = await self._pool.fetch(
                "SELECT kind, id, document, version, updated_at FROM config_documents"
            )
        except Exception as exc:  # noqa: BLE001 - any DB/driver failure keeps the old snapshot
            log.error("config_reload_failed", extra={"error": f"{type(exc).__name__}: {exc}"})
            return False
        snapshot = self._build_snapshot(rows)
        self._fingerprint = (
            max((row["updated_at"] for row in rows), default=None),
            len(rows),
        )
        self._snapshot = snapshot
        for callback in self.on_reload:
            try:
                callback(snapshot)
            except Exception:  # noqa: BLE001 - one bad subscriber must not block the others
                log.exception("config_reload_callback_failed")
        log.info(
            "config_reloaded",
            extra={"documents": sum(len(v) for v in snapshot.documents.values())},
        )
        return True

    def _build_snapshot(self, rows: list[Any]) -> ConfigSnapshot:
        previous = self._snapshot
        known = {spec.kind for spec in registered_kinds()}
        documents: dict[str, dict[str, BaseModel]] = {kind: {} for kind in known}
        versions: dict[tuple[str, str], int] = {}
        for row in rows:
            kind, document_id = row["kind"], row["id"]
            if kind not in known:
                continue
            try:
                model = get_kind(kind).validate_document(row["document"])
            except Exception as exc:  # noqa: BLE001 - one bad row must not block the rest
                log.error(
                    "config_document_invalid",
                    extra={"kind": kind, "config_id": document_id, "error": str(exc)},
                )
                old = previous.of_kind(kind).get(document_id)
                if old is not None:
                    documents[kind][document_id] = old
                    versions[(kind, document_id)] = previous.versions[(kind, document_id)]
                continue
            documents[kind][document_id] = model
            versions[(kind, document_id)] = row["version"]
        return ConfigSnapshot(
            MappingProxyType({k: MappingProxyType(v) for k, v in documents.items()}),
            MappingProxyType(versions),
        )

    async def start(self, pool: asyncpg.Pool, redis: Redis) -> None:
        """Subscribe (await confirmation), then load with retries; raise if it never loads."""
        self._pool = pool
        self._subscribed.clear()
        deadline = time.monotonic() + self._initial_load_timeout
        self._tasks = [
            asyncio.create_task(self._listen(redis), name="config-registry-listener"),
            asyncio.create_task(self._reconcile(), name="config-registry-reconcile"),
        ]
        try:
            await asyncio.wait_for(self._subscribed.wait(), timeout=self._initial_load_timeout)
            delay = 0.25
            while not await self.reload():
                if time.monotonic() + delay > deadline:
                    raise RuntimeError("configuration could not be loaded from the database")
                await asyncio.sleep(delay)
                delay = min(delay * 2, _MAX_BACKOFF_SECONDS)
        except BaseException:
            # Never leave the listener or reconcile task running after a failed start.
            await self.stop()
            raise

    async def stop(self) -> None:
        """Cancel the listener, the reconcile loop and pending reloads."""
        tasks = [*self._tasks, *self._pending]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks = []
        self._pending.clear()

    def _request_reload(self) -> None:
        task = asyncio.create_task(self.reload(), name="config-registry-reload")
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _listen(self, redis: Redis) -> None:
        """Subscribe, wait for the confirmation, reload, then listen; repeat after any failure."""
        is_first = True
        backoff = 0.5
        while True:
            pubsub = redis.pubsub()
            try:
                await pubsub.subscribe(CONFIG_CHANGED_CHANNEL)
                await self._await_subscribe_confirmation(pubsub)
                backoff = 0.5
                self._subscribed.set()
                if not is_first:
                    # A message may have been missed while disconnected.
                    self._request_reload()
                is_first = False
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        self._request_reload()
            except Exception as exc:  # noqa: BLE001 - the listener must never die silently
                log.error(
                    "config_subscription_failed", extra={"error": f"{type(exc).__name__}: {exc}"}
                )
                is_first = False
            finally:
                with contextlib.suppress(Exception):
                    await pubsub.aclose()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_SECONDS)

    @staticmethod
    async def _await_subscribe_confirmation(pubsub: Any) -> None:
        for _ in range(10):
            message = await pubsub.get_message(timeout=1.0)
            if message is not None and message["type"] == "subscribe":
                return
        raise RuntimeError("no subscribe confirmation from Redis")

    async def _reconcile(self) -> None:
        """Reload when the table changed without a notification reaching us."""
        while True:
            await asyncio.sleep(self._reconcile_interval)
            try:
                if self._pool is None:
                    continue
                row = await self._pool.fetchrow(
                    "SELECT max(updated_at) AS latest, count(*) AS total FROM config_documents"
                )
                if (row["latest"], row["total"]) != self._fingerprint:
                    log.warning("config_reconcile_reload")
                    await self.reload()
            except Exception as exc:  # noqa: BLE001 - keep reconciling
                log.error("config_reconcile_failed", extra={"error": str(exc)})
