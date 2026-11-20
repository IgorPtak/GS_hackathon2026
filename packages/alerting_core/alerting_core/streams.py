"""Consumer-group reader with the failure semantics every worker shares.

Guarantees (contracts/storage.md):
- an entry is acknowledged only after the handler succeeded for it, so a crash never loses it;
- entries pending longer than `min_idle_seconds` (their consumer died or failed them) are taken
  over with XAUTOCLAIM by any consumer of the group;
- an entry delivered `max_deliveries` times without an ack is a poison entry: it is copied to
  `<stream>-dlq` with its original fields plus `error` and `attempts`, then acknowledged, so it
  stops being retried.
Handlers must therefore be idempotent: an entry can be handled more than once.
"""

import asyncio
import os
import socket
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from .logging import get_logger
from .metrics import STREAM_BATCH_SECONDS, STREAM_MESSAGES

log = get_logger(__name__)

# Bound memory of the last error per entry; only used to explain DLQ entries.
_MAX_REMEMBERED_ERRORS = 10_000


@dataclass(frozen=True, slots=True)
class StreamMessage:
    """One stream entry. `fields` keep Redis bytes; producers write orjson values.

    `delivery_count` is 1 for a fresh read and the PEL counter for a reclaimed entry, so a
    handler can tell a retry from a first attempt.
    """

    id: str
    fields: dict[bytes, bytes]
    delivery_count: int = 1


# Message id -> error text for entries the handler could not process. They stay pending and are
# retried after `min_idle_seconds`; every other entry of the batch is acknowledged.
BatchFailures = Mapping[str, str]
BatchHandler = Callable[[list[StreamMessage]], Awaitable[BatchFailures | None]]


def dead_letter_stream(stream: str) -> str:
    """`<stream>-dlq`, the single DLQ naming rule from contracts/storage.md."""
    return f"{stream}-dlq"


def default_consumer_name(service_name: str) -> str:
    """`<service>-<hostname>-<pid>`: unique per process, readable in XINFO CONSUMERS."""
    return f"{service_name}-{socket.gethostname()}-{os.getpid()}"


def _as_text(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


class StreamConsumer:
    """Reads one stream as one consumer of a group and feeds batches to a handler.

    Usage: `await StreamConsumer(redis, "events", "processors", name, handle_batch).run(stop)`.
    """

    def __init__(
        self,
        redis: Redis,
        stream: str,
        group: str,
        consumer: str,
        handler: BatchHandler,
        *,
        batch_size: int = 100,
        block_ms: int = 1000,
        min_idle_seconds: float = 30.0,
        claim_interval_seconds: float = 5.0,
        max_deliveries: int = 5,
        dead_letter_maxlen: int = 100_000,
    ) -> None:
        self._redis = redis
        self.stream = stream
        self.group = group
        self.consumer = consumer
        self._handler = handler
        self._batch_size = batch_size
        self._block_ms = block_ms
        self._min_idle_ms = int(min_idle_seconds * 1000)
        self._claim_interval = claim_interval_seconds
        self._max_deliveries = max_deliveries
        self._dead_letter_maxlen = dead_letter_maxlen
        self._claim_cursor = "0-0"
        self._next_claim_at = 0.0
        self._last_errors: dict[str, str] = {}

    async def ensure_group(self) -> None:
        """Create the group (and the stream) if missing; start at 0 so earlier entries count."""
        try:
            await self._redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    async def run(self, stop: asyncio.Event) -> None:
        """Loop until `stop` is set: reclaim idle entries periodically, read and handle new ones."""
        log.info("stream_consumer_started", extra=self._log_fields())
        is_group_ready = False
        while not stop.is_set():
            try:
                if not is_group_ready:
                    # Inside the loop so a Redis that is down at startup, or restarted without
                    # persistence, is retried instead of killing the worker.
                    await self.ensure_group()
                    is_group_ready = True
                if time.monotonic() >= self._next_claim_at:
                    await self._reclaim_safely()
                await self.read_once()
            except asyncio.CancelledError:
                raise
            except ResponseError as error:
                if "NOGROUP" in str(error):
                    is_group_ready = False
                log.exception("stream_consumer_error", extra=self._log_fields())
                await asyncio.sleep(1.0)
            except Exception:
                # Redis hiccup or a bug outside the handler: nothing was acked, so nothing is
                # lost; back off briefly instead of spinning.
                log.exception("stream_consumer_error", extra=self._log_fields())
                await asyncio.sleep(1.0)
        log.info("stream_consumer_stopped", extra=self._log_fields())

    async def _reclaim_safely(self) -> None:
        # Scheduled before running so a reclaim that keeps failing never starves new reads.
        self._next_claim_at = time.monotonic() + self._claim_interval
        try:
            # A full batch means more idle entries may wait (e.g. after a crash): keep going.
            while await self.reclaim_idle() >= self._batch_size:
                pass
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("stream_reclaim_failed", extra=self._log_fields())

    async def read_once(self) -> int:
        """Read one batch of new entries for this consumer and handle it; returns its size."""
        response = await self._redis.xreadgroup(
            self.group,
            self.consumer,
            {self.stream: ">"},
            count=self._batch_size,
            block=self._block_ms,
        )
        messages = [
            StreamMessage(id=_as_text(entry_id), fields=fields or {})
            for _, entries in response or []
            for entry_id, fields in entries
        ]
        if messages:
            await self._handle(messages)
        return len(messages)

    async def reclaim_idle(self) -> int:
        """Dead-letter poison entries, then take over and handle other idle entries.

        Returns the number of entries handled (dead-lettered entries are not counted).
        """
        pending = await self._redis.xpending_range(
            self.stream,
            self.group,
            min="-",
            max="+",
            count=self._batch_size,
            idle=self._min_idle_ms,
        )
        delivery_counts = {
            _as_text(entry["message_id"]): int(entry["times_delivered"]) for entry in pending
        }
        poison_ids = [
            entry_id for entry_id, count in delivery_counts.items() if count >= self._max_deliveries
        ]
        for entry_id in poison_ids:
            try:
                await self._dead_letter_pending(entry_id, delivery_counts[entry_id])
            except Exception:
                # One entry that cannot be moved must not block the others; retried next pass.
                log.exception(
                    "stream_dead_letter_failed", extra={**self._log_fields(), "entry_id": entry_id}
                )

        if len(poison_ids) == len(delivery_counts):
            return 0
        next_cursor, claimed, *_ = await self._redis.xautoclaim(
            self.stream,
            self.group,
            self.consumer,
            min_idle_time=self._min_idle_ms,
            start_id=self._claim_cursor,
            count=self._batch_size,
        )
        # The cursor walks the PEL in slices; "0-0" means the walk wrapped around.
        self._claim_cursor = _as_text(next_cursor)
        messages = [
            StreamMessage(
                id=_as_text(entry_id),
                fields=fields,
                # XAUTOCLAIM itself counts as a delivery.
                delivery_count=delivery_counts.get(_as_text(entry_id), 0) + 1,
            )
            for entry_id, fields in claimed
            # Entries trimmed from the stream come back without fields; nothing to handle.
            if fields
        ]
        if messages:
            STREAM_MESSAGES.labels(self.stream, self.group, "claimed").inc(len(messages))
            log.info("stream_entries_claimed", extra={**self._log_fields(), "count": len(messages)})
            await self._handle(messages)
        return len(messages)

    async def dead_letter(self, messages: list[StreamMessage], error: str) -> None:
        """Move entries the handler knows can never succeed (e.g. invalid JSON) to the DLQ now."""
        for message in messages:
            await self._move_to_dead_letter(
                message.id, message.fields, error, message.delivery_count
            )

    async def _handle(self, messages: list[StreamMessage]) -> None:
        started = time.perf_counter()
        try:
            failures = await self._handler(messages) or {}
        except Exception as error:
            # The whole batch stays pending and is retried after min_idle via XAUTOCLAIM.
            failures = {message.id: f"{type(error).__name__}: {error}" for message in messages}
            log.exception(
                "stream_batch_failed", extra={**self._log_fields(), "count": len(messages)}
            )
        finally:
            STREAM_BATCH_SECONDS.labels(self.stream, self.group).observe(
                time.perf_counter() - started
            )

        acked_ids = [message.id for message in messages if message.id not in failures]
        if acked_ids:
            await self._redis.xack(self.stream, self.group, *acked_ids)
            STREAM_MESSAGES.labels(self.stream, self.group, "acked").inc(len(acked_ids))
        if failures:
            STREAM_MESSAGES.labels(self.stream, self.group, "failed").inc(len(failures))
            self._remember_errors(failures)
        for entry_id in acked_ids:
            self._last_errors.pop(entry_id, None)

    async def _dead_letter_pending(self, entry_id: str, delivery_count: int) -> None:
        entries = await self._redis.xrange(self.stream, min=entry_id, max=entry_id)
        fields = entries[0][1] if entries else {}
        error = self._last_errors.pop(
            entry_id, f"not acknowledged after {delivery_count} deliveries"
        )
        await self._move_to_dead_letter(entry_id, fields, error, delivery_count)

    async def _move_to_dead_letter(
        self, entry_id: str, fields: dict[bytes, bytes], error: str, attempts: int
    ) -> None:
        # XADD + XACK in one MULTI: the entry is never both lost and acknowledged.
        async with self._redis.pipeline(transaction=True) as pipeline:
            if fields:
                pipeline.xadd(
                    dead_letter_stream(self.stream),
                    {**fields, b"error": error.encode(), b"attempts": str(attempts).encode()},
                    maxlen=self._dead_letter_maxlen,
                    approximate=True,
                )
            pipeline.xack(self.stream, self.group, entry_id)
            await pipeline.execute()
        # Without fields the entry was already trimmed from the stream: nothing could be copied.
        outcome = "dead_lettered" if fields else "dropped_trimmed"
        STREAM_MESSAGES.labels(self.stream, self.group, outcome).inc()
        log.warning(
            "stream_entry_dead_lettered" if fields else "stream_entry_dropped_trimmed",
            extra={**self._log_fields(), "entry_id": entry_id, "attempts": attempts}
            | {"error": error},
        )

    def _remember_errors(self, failures: BatchFailures) -> None:
        if len(self._last_errors) > _MAX_REMEMBERED_ERRORS:
            self._last_errors.clear()
        self._last_errors.update(failures)

    def _log_fields(self) -> dict[str, str]:
        return {"stream": self.stream, "group": self.group, "consumer": self.consumer}
