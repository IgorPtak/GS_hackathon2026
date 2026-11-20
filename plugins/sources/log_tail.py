"""Log-file tail source: follows a file and turns each line into one event.

Not an HTTP plugin. Ingest starts one `LogTailRunner` per enabled `log_tail` source; the runner
owns a Redis lock so only one worker process tails a given file, and stores its read offset so a
restart resumes without gaps.
"""

import asyncio
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

import orjson
from alerting_contracts.config import SourceConfig
from alerting_contracts.events import EventEnvelope, SourceType
from alerting_core.logging import get_logger
from redis.asyncio.client import Redis
from redis.exceptions import RedisError
from ulid import ULID

log = get_logger(__name__)

POLL_SECONDS = 0.2
LOCK_TTL_MS = 10_000
LOCK_RENEW_SECONDS = 3.0
LOCK_RETRY_SECONDS = 5.0
BATCH_LINES = 500
READ_BYTES = 1 << 20
DLQ_STREAM = "events-dlq"
DLQ_MAXLEN = 100_000

AppendFn = Callable[[list[EventEnvelope]], Awaitable[Any]]

# Renew/release only while we still own the lock, so a stalled owner cannot touch a successor's.
RENEW_SCRIPT = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('PEXPIRE', KEYS[1], ARGV[2]) else return 0 end"
)
RELEASE_SCRIPT = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('DEL', KEYS[1]) else return 0 end"
)


class LineParseError(ValueError):
    """A log line does not match the configured format."""


def parse_line(line: str, source: SourceConfig, pattern: re.Pattern[str] | None) -> dict[str, Any]:
    """Parse one line into a payload (named groups or JSON object) plus `raw_line`.

    Values stay strings for regex: rules coerce types, so ingest must not guess.
    """
    if source.settings.get("line_format", "json") == "json":
        try:
            parsed = orjson.loads(line)
        except orjson.JSONDecodeError as error:
            raise LineParseError(f"line is not valid JSON: {error}") from None
        if not isinstance(parsed, dict):
            raise LineParseError("JSON line is not an object")
        return {**parsed, "raw_line": line}
    if pattern is None:
        raise LineParseError("line_pattern is missing or invalid")
    match = pattern.match(line)
    if match is None:
        raise LineParseError("line does not match line_pattern")
    groups = {key: value for key, value in match.groupdict().items() if value is not None}
    return {**groups, "raw_line": line}


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
        self._pattern = self._compile_pattern()
        # Lines read but not yet appended, as (decoded line, bytes consumed incl. newline).
        self._queue: list[tuple[str, int]] = []
        self._partial = b""
        self._offset = 0
        self._inode = 0
        self._last_renew = 0.0
        self._warned_missing = False

    def _compile_pattern(self) -> re.Pattern[str] | None:
        raw = self.source.settings.get("line_pattern")
        if not raw:
            return None
        try:
            return re.compile(raw)
        except re.error as error:
            log.error(
                "log_tail_pattern_invalid",
                extra={"source_id": self.source.id, "error": str(error)},
            )
            return None

    async def run(self) -> None:
        """Acquire the lock, tail while holding it, hand over on loss; runs until cancelled."""
        try:
            while True:
                if await self._acquire_lock():
                    log.info(
                        "log_tail_started",
                        extra={"source_id": self.source.id, "path": self._path},
                    )
                    await self._tail_while_locked()
                else:
                    await asyncio.sleep(LOCK_RETRY_SECONDS)
        except asyncio.CancelledError:
            await self._release_lock()
            raise

    async def _acquire_lock(self) -> bool:
        try:
            got = await self._redis.set(self._lock_key, self._token, nx=True, px=LOCK_TTL_MS)
        except RedisError as error:
            log.error(
                "log_tail_redis_error", extra={"source_id": self.source.id, "error": str(error)}
            )
            return False
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
        self._queue, self._partial = [], b""
        handle = None
        try:
            while True:
                if time.monotonic() - self._last_renew >= LOCK_RENEW_SECONDS:
                    if not await self._renew_lock():
                        log.warning("log_tail_lock_lost", extra={"source_id": self.source.id})
                        return
                    self._last_renew = time.monotonic()
                try:
                    handle = await self._step(handle)
                except RedisError as error:
                    log.error(
                        "log_tail_redis_error",
                        extra={"source_id": self.source.id, "error": str(error)},
                    )
                await asyncio.sleep(POLL_SECONDS)
        finally:
            if handle is not None:
                handle.close()

    async def _step(self, handle: Any) -> Any:
        """One poll: (re)open if needed, read new bytes, flush queued lines. Returns the handle."""
        if self._queue:
            await self._flush()  # A previous append failed; do not read past unsent lines.
            return handle
        if handle is None:
            handle = await self._open()
            if handle is None:
                return None
        position = handle.tell()
        chunk = handle.read(READ_BYTES)
        if chunk:
            self._ingest_chunk(chunk)
            await self._flush()
            return handle
        # At EOF: check whether the path now points at a different file or was truncated.
        try:
            path_inode: int | None = os.stat(self._path).st_ino
        except FileNotFoundError:
            path_inode = None
        is_truncated = os.fstat(handle.fileno()).st_size < position
        if path_inode != self._inode or is_truncated:
            handle.close()
            log.info("log_tail_rotated", extra={"source_id": self.source.id})
            self._partial = b""
            self._offset = 0
            # Reset under the old inode so a restart cannot resume at a stale offset.
            await self._store_offset()
            return None
        return handle

    async def _open(self) -> Any:
        """Open the file and position it from the stored offset or `start_at`."""
        try:
            handle = open(self._path, "rb")  # noqa: SIM115, ASYNC230  (kept open across polls; local open and read are fast)
        except OSError:
            if not self._warned_missing:
                log.warning(
                    "log_tail_file_missing",
                    extra={"source_id": self.source.id, "path": self._path},
                )
                self._warned_missing = True
            return None
        self._warned_missing = False
        stat = os.fstat(handle.fileno())
        stored = await self._load_offset()
        if stored is not None and stored[0] == stat.st_ino and stored[1] <= stat.st_size:
            start = stored[1]
        elif stored is not None:
            start = 0  # Rotated or truncated while we were not running: read the new file fully.
        elif self.source.settings.get("start_at", "end") == "beginning":
            start = 0
        else:
            start = stat.st_size
        handle.seek(start)
        self._inode = stat.st_ino
        self._offset = start
        self._partial = b""
        return handle

    def _ingest_chunk(self, chunk: bytes) -> None:
        """Split into complete lines; the unterminated tail waits for its newline."""
        data = self._partial + chunk
        *lines, self._partial = data.split(b"\n")
        for raw in lines:
            self._queue.append((raw.decode("utf-8", errors="replace").rstrip("\r"), len(raw) + 1))

    async def _flush(self) -> None:
        """Append queued lines in batches, then persist the offset after each success."""
        while self._queue:
            batch = self._queue[:BATCH_LINES]
            envelopes: list[EventEnvelope] = []
            now = datetime.now(UTC)
            for line, _ in batch:
                if not line.strip():
                    continue
                try:
                    payload = parse_line(line, self.source, self._pattern)
                except LineParseError as error:
                    await self._send_to_dlq(line, str(error), now)
                    continue
                envelopes.append(self._envelope(payload, now))
            if envelopes:
                await self._append(envelopes)
            del self._queue[: len(batch)]
            self._offset += sum(size for _, size in batch)
            await self._store_offset()

    def _envelope(self, payload: dict[str, Any], received_at: datetime) -> EventEnvelope:
        return EventEnvelope(
            event_id=str(ULID()),
            idempotency_key=None,
            source_id=self.source.id,
            source_type=SourceType.log_tail,
            received_at=received_at,
            payload=payload,
        )

    async def _send_to_dlq(self, line: str, error: str, received_at: datetime) -> None:
        envelope = self._envelope({"raw_line": line}, received_at)
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

    async def _load_offset(self) -> tuple[int, int] | None:
        raw = await self._redis.get(self._offset_key)
        if raw is None:
            return None
        inode, _, offset = raw.decode().partition(":")
        return int(inode), int(offset)

    async def _store_offset(self) -> None:
        await self._redis.set(self._offset_key, f"{self._inode}:{self._offset}")
