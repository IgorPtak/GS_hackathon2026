"""Log-file tail source: follows a file and turns each line into one event.

Not an HTTP plugin. Ingest starts one `LogTailRunner` per enabled `log_tail` source; the runner
owns a Redis lock so only one worker process tails a given file, and stores its read offset so a
restart or lock handover resumes without gaps. Each event gets the key
`<source_id>:<inode>:<generation>:<line_start_offset>`, so a re-read line is dropped by ingest.
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, BinaryIO

import orjson
from alerting_contracts.config import SourceConfig
from alerting_contracts.events import EventEnvelope, SourceType
from alerting_core.logging import get_logger
from redis.asyncio.client import Redis
from redis.exceptions import RedisError
from ulid import ULID

from ._log_files import (
    RELEASE_SCRIPT,
    RENEW_SCRIPT,
    FileIdentity,
    LineParseError,
    LineSplitter,
    QueuedLine,
    compile_pattern,
    open_file,
    parse_line,
    poll_file,
)

log = get_logger(__name__)

POLL_SECONDS = 0.2
LOCK_TTL_MS = 10_000
LOCK_RENEW_SECONDS = 3.0
LOCK_RETRY_SECONDS = 5.0
ERROR_RETRY_SECONDS = 5.0
BATCH_LINES = 500
READ_BYTES = 1 << 20
DLQ_STREAM = "events-dlq"
DLQ_MAXLEN = 100_000

AppendFn = Callable[[list[EventEnvelope]], Awaitable[Any]]


class LogTailRunner:
    """Tails `settings.path` for one source and appends parsed lines through `append`."""

    def __init__(self, source: SourceConfig, redis: Redis, append: AppendFn) -> None:
        self.source = source
        self._redis = redis
        self._append = append
        self._path = str(source.settings.get("path", ""))
        self._token = uuid.uuid4().hex
        self._lock_key = f"log-tail-lock:{source.id}"
        self._offset_key = f"log-tail-offset:{source.id}"
        self._pattern = compile_pattern(source)
        self._queue: list[QueuedLine] = []
        self._splitter = LineSplitter()
        self._offset = 0  # committed: everything before it has been appended
        self._identity: FileIdentity = (0, 0)
        # Bumped on every truncation or new file so keys never repeat for the same offsets.
        self._generation = 0
        self._head = b""  # first bytes of the file, to notice truncate-and-regrow
        self._last_renew = 0.0
        self._was_missing = False  # file was absent when first looked for: start_at=end is moot
        self._warned_missing = False

    async def run(self) -> None:
        """Acquire the lock, tail while holding it, hand over on loss; runs until cancelled."""
        try:
            while True:
                try:
                    if await self._acquire_lock():
                        log.info(
                            "log_tail_started",
                            extra={"source_id": self.source.id, "path": self._path},
                        )
                        await self._tail_while_locked()
                    else:
                        await asyncio.sleep(LOCK_RETRY_SECONDS)
                except Exception as error:  # noqa: BLE001  (a tail must never die silently)
                    log.error(
                        "log_tail_error", extra={"source_id": self.source.id, "error": str(error)}
                    )
                    await self._release_lock()
                    await asyncio.sleep(ERROR_RETRY_SECONDS)
        except asyncio.CancelledError:
            await self._release_lock()
            raise

    async def _acquire_lock(self) -> bool:
        got = await self._redis.set(self._lock_key, self._token, nx=True, px=LOCK_TTL_MS)
        self._last_renew = time.monotonic()
        return bool(got)

    async def _renew_lock(self) -> bool:
        try:
            result = await self._redis.eval(
                RENEW_SCRIPT, 1, self._lock_key, self._token, LOCK_TTL_MS
            )
        except RedisError:
            return False
        return bool(result)

    async def _release_lock(self) -> None:
        try:
            await self._redis.eval(RELEASE_SCRIPT, 1, self._lock_key, self._token)
        except RedisError:
            pass  # The lock expires on its own after LOCK_TTL_MS.

    async def _tail_while_locked(self) -> None:
        """Follow the file across rotations until the lock is lost."""
        self._splitter.reset()
        self._queue = []
        handle: BinaryIO | None = None
        try:
            while True:
                if time.monotonic() - self._last_renew >= LOCK_RENEW_SECONDS:
                    if not await self._renew_lock():
                        log.warning("log_tail_lock_lost", extra={"source_id": self.source.id})
                        return
                    self._last_renew = time.monotonic()
                try:
                    handle, is_busy = await self._step(handle)
                except RedisError as error:
                    is_busy = False
                    log.error(
                        "log_tail_redis_error",
                        extra={"source_id": self.source.id, "error": str(error)},
                    )
                if not is_busy:
                    await asyncio.sleep(POLL_SECONDS)
        finally:
            if handle is not None:
                handle.close()

    async def _step(self, handle: BinaryIO | None) -> tuple[BinaryIO | None, bool]:
        """One poll; returns (handle, True when a full read suggests more data is waiting)."""
        if self._queue:
            await self._flush()  # A previous append failed; do not read past unsent lines.
            return handle, False
        if handle is None:
            handle = await self._open()
            if handle is None:
                return None, False
        size, position, path_identity, head = await asyncio.to_thread(poll_file, handle, self._path)
        # A changed head with size >= position is a truncate-and-regrow between two polls.
        if size < position or head[: len(self._head)] != self._head:
            log.info("log_tail_truncated", extra={"source_id": self.source.id})
            await asyncio.to_thread(handle.seek, 0)
            self._generation += 1
            self._head = head
            self._splitter.reset(0)
            self._offset = 0
            await self._store_offset()
            return handle, True
        if len(head) > len(self._head):
            self._head = head  # A short file grew: keep comparing against the longer head.
        chunk = await asyncio.to_thread(handle.read, READ_BYTES)
        if chunk:
            self._queue.extend(self._splitter.split(chunk))
            await self._flush()
            return handle, len(chunk) == READ_BYTES
        if path_identity == self._identity:
            return handle, False
        # The path now points at another file (or none): the old one is fully drained.
        log.info("log_tail_rotated", extra={"source_id": self.source.id})
        last_line = self._splitter.take_partial()  # A writer that never ends its last line.
        if last_line is not None:
            self._queue.append(last_line)
        await self._flush()
        handle.close()
        self._generation += 1
        self._splitter.reset(0)
        self._offset = 0
        # Reset under the old inode so a restart cannot resume at a stale offset.
        await self._store_offset()
        return None, False

    async def _open(self) -> BinaryIO | None:
        """Open the file and position it from the stored offset or `start_at`."""
        opened = await asyncio.to_thread(open_file, self._path)
        if opened is None:
            self._was_missing = True
            if not self._warned_missing:
                log.warning(
                    "log_tail_file_missing",
                    extra={"source_id": self.source.id, "path": self._path},
                )
                self._warned_missing = True
            return None
        handle, identity, size, head = opened
        self._warned_missing = False
        stored = await self._load_offset()
        if stored is None:
            self._generation = 0
            is_end = self.source.settings.get("start_at", "end") == "end"
            # A file created after we started waiting is all new.
            start = size if is_end and not self._was_missing else 0
        elif stored[0] == identity[0] and stored[2] <= size:
            self._generation, start = stored[1], stored[2]
        else:
            # Rotated or truncated while we were not running: new generation, read it fully.
            self._generation, start = stored[1] + 1, 0
        await asyncio.to_thread(handle.seek, start)
        self._identity = identity
        self._head = head
        self._splitter.reset(start)
        self._offset = start
        # Persist now so a lock handover resumes here instead of re-applying start_at.
        await self._store_offset()
        return handle

    async def _flush(self) -> None:
        """Append queued lines in batches, then persist the offset after each success."""
        while self._queue:
            batch = self._queue[:BATCH_LINES]
            envelopes: list[EventEnvelope] = []
            now = datetime.now(UTC)
            for item in batch:
                if item.error is not None:
                    await self._send_to_dlq(item.text, item.error, now)
                elif item.text.strip():
                    try:
                        payload = parse_line(item.text, self.source, self._pattern)
                    except LineParseError as error:
                        await self._send_to_dlq(item.text, str(error), now)
                    else:
                        key = (
                            f"{self.source.id}:{self._identity[0]}:{self._generation}:{item.start}"
                        )
                        envelopes.append(self._envelope(payload, now, key))
            if envelopes:
                await self._append(envelopes)
            del self._queue[: len(batch)]
            self._offset = batch[-1].start + batch[-1].size
            await self._store_offset()

    def _envelope(
        self, payload: dict[str, Any], received_at: datetime, key: str | None
    ) -> EventEnvelope:
        return EventEnvelope(
            event_id=str(ULID()),
            idempotency_key=key,
            source_id=self.source.id,
            source_type=SourceType.log_tail,
            received_at=received_at,
            payload=payload,
        )

    async def _send_to_dlq(self, line: str, error: str, received_at: datetime) -> None:
        envelope = self._envelope({"raw_line": line}, received_at, None)
        await self._redis.xadd(
            DLQ_STREAM,
            {
                "envelope": orjson.dumps(envelope.model_dump(mode="json")),
                "error": error,
                "attempts": 1,
            },
            maxlen=DLQ_MAXLEN,
            approximate=True,
        )

    async def _load_offset(self) -> tuple[int, int, int] | None:
        """Stored (inode, generation, offset); the old `inode:offset` form is generation 0."""
        raw = await self._redis.get(self._offset_key)
        if raw is None:
            return None
        try:
            parts = [int(part) for part in raw.decode().split(":")]
            if len(parts) == 2:
                return parts[0], 0, parts[1]
            if len(parts) == 3:
                return parts[0], parts[1], parts[2]
        except ValueError:
            pass
        log.warning("log_tail_offset_corrupt", extra={"source_id": self.source.id})
        return None

    async def _store_offset(self) -> None:
        value = f"{self._identity[0]}:{self._generation}:{self._offset}"
        await self._redis.set(self._offset_key, value)
