"""In-memory typed configuration snapshots, reloaded when `config.changed` arrives.

A snapshot is immutable and replaced in one assignment, so readers never see a half-loaded state.
Reload re-reads every document from Postgres; if any fails validation the previous snapshot stays.
"""

import asyncio
import contextlib
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
from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from ..logging import get_logger
from .kinds import get_kind, registered_kinds
from .store import CONFIG_CHANGED_CHANNEL

log = get_logger(__name__)

_RESUBSCRIBE_DELAY_SECONDS = 1.0


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

    def __init__(self) -> None:
        self._snapshot = ConfigSnapshot()
        self._pool: asyncpg.Pool | None = None
        self._task: asyncio.Task[None] | None = None
        self._subscribed = asyncio.Event()
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
        return self._snapshot.of_kind("schema")

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
        """Re-read all documents from the DB and swap the snapshot. False if kept the old one."""
        if self._pool is None:
            raise RuntimeError("ConfigRegistry.start() has not been called")
        try:
            snapshot = await self._build_snapshot(self._pool)
        except (ValidationError, ValueError, asyncpg.PostgresError, OSError) as exc:
            log.error("config_reload_failed", extra={"error": str(exc)})
            return False
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

    async def _build_snapshot(self, pool: asyncpg.Pool) -> ConfigSnapshot:
        known = {spec.kind for spec in registered_kinds()}
        rows = await pool.fetch("SELECT kind, id, document, version FROM config_documents")
        documents: dict[str, dict[str, BaseModel]] = {kind: {} for kind in known}
        versions: dict[tuple[str, str], int] = {}
        for row in rows:
            if row["kind"] not in known:
                continue
            try:
                model = get_kind(row["kind"]).validate_document(row["document"])
            except ValidationError as exc:
                raise ValueError(f"{row['kind']}/{row['id']}: {exc}") from exc
            documents[row["kind"]][row["id"]] = model
            versions[(row["kind"], row["id"])] = row["version"]
        return ConfigSnapshot(
            MappingProxyType({k: MappingProxyType(v) for k, v in documents.items()}),
            MappingProxyType(versions),
        )

    async def start(self, pool: asyncpg.Pool, redis: Redis) -> None:
        """Subscribe to `config.changed`, then load, so no change between the two is missed."""
        self._pool = pool
        self._subscribed.clear()
        self._task = asyncio.create_task(self._listen(redis), name="config-registry-listener")
        await asyncio.wait_for(self._subscribed.wait(), timeout=10)
        await self.reload()

    async def stop(self) -> None:
        """Cancel the subscription task."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _listen(self, redis: Redis) -> None:
        while True:
            pubsub = redis.pubsub()
            try:
                await pubsub.subscribe(CONFIG_CHANGED_CHANNEL)
                self._subscribed.set()
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        await self.reload()
            except RedisError as exc:
                log.error("config_subscription_failed", extra={"error": str(exc)})
            finally:
                with contextlib.suppress(RedisError):
                    await pubsub.aclose()
            await asyncio.sleep(_RESUBSCRIBE_DELAY_SECONDS)
            # A message may have been missed while disconnected.
            await self.reload()
