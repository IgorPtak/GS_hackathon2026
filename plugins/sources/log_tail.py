"""Log-file tail source: follows a file and turns each line into one event.

Not an HTTP plugin. Ingest starts one `LogTailRunner` per enabled `log_tail` source; the runner
owns a Redis lock so only one worker process tails a given file, and stores its read offset so a
restart or lock handover resumes without gaps. Each event gets the key
`<source_id>:<inode>:<line_start_offset>`, so any re-read line is dropped by ingest's SET NX.
"""

import asyncio
import os
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, BinaryIO, NamedTuple

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
ERROR_RETRY_SECONDS = 5.0
BATCH_LINES = 500
READ_BYTES = 1 << 20
MAX_LINE_BYTES = 1 << 20
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


class QueuedLine(NamedTuple):
    """One complete line read from the file, waiting to be appended."""

    text: str
    start: int  # byte offset of the line start in the file
    size: int  # bytes consumed, including the newline when there was one
    error: str | None = None  # set for lines that go straight to the DLQ


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


def open_file(path: str) -> tuple[BinaryIO, int, int] | None:
    """Blocking: open `path`; returns (handle, inode, size) or None when it does not exist."""
    try:
        handle = open(path, "rb")  # noqa: SIM115  (kept open across polls)
    except OSError:
        return None
    stat = os.fstat(handle.fileno())
    return handle, stat.st_ino, stat.st_size


def poll_file(handle: BinaryIO, path: str) -> tuple[int, int, int | None]:
    """Blocking: (size of the open file, our read position, inode now at `path` or None)."""
    try:
        path_inode: int | None = os.stat(path).st_ino
    except OSError:
        path_inode = None
    return os.fstat(handle.fileno()).st_size, handle.tell(), path_inode


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
        self._queue: list[QueuedLine] = []
        self._partial = b""  # bytes of the current unterminated line
        self._skip_prefix: str | None = None  # set while discarding an over-long line
        self._skip_size = 0
        self._line_start = 0  # file offset where the current line began
        self._offset = 0  # committed: everything before it has been appended
        self._inode = 0
        self._last_renew = 0.0
        self._was_missing = False  # file was absent when first looked for: start_at=end is moot
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
        self._reset_buffers()
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

    def _reset_buffers(self) -> None:
        self._partial = b""
        self._skip_prefix = None
        self._skip_size = 0

    async def _step(self, handle: BinaryIO | None) -> tuple[BinaryIO | None, bool]:
        """One poll; returns (handle, True when a full read suggests more data is waiting)."""
        if self._queue:
            await self._flush()  # A previous append failed; do not read past unsent lines.
            return handle, False
        if handle is None:
            handle = await self._open()
            if handle is None:
                return None, False
        size, position, path_inode = await asyncio.to_thread(poll_file, handle, self._path)
        if size < position:
            log.info("log_tail_truncated", extra={"source_id": self.source.id})
            await asyncio.to_thread(handle.seek, 0)
            self._reset_buffers()
            self._line_start = self._offset = 0
            await self._store_offset()
            return handle, True
        chunk = await asyncio.to_thread(handle.read, READ_BYTES)
        if chunk:
            self._split_lines(chunk)
            await self._flush()
            return handle, len(chunk) == READ_BYTES
        if path_inode == self._inode:
            return handle, False
        # The path now points at another file (or none): the old one is fully drained.
        log.info("log_tail_rotated", extra={"source_id": self.source.id})
        if self._partial:
            # A writer that never ends its last line must not lose it.
            self._queue.append(
                QueuedLine(self._decode(self._partial), self._line_start, len(self._partial))
            )
        await self._flush()
        handle.close()
        self._reset_buffers()
        self._line_start = self._offset = 0
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
        handle, inode, size = opened
        self._warned_missing = False
        stored = await self._load_offset()
        if stored is not None and stored[0] == inode and stored[1] <= size:
            start = stored[1]
        elif stored is not None:
            start = 0  # Rotated or truncated while we were not running: read the new file fully.
        elif self.source.settings.get("start_at", "end") == "end" and not self._was_missing:
            start = size
        else:
            start = 0  # A file created after we started waiting is all new.
        await asyncio.to_thread(handle.seek, start)
        self._inode = inode
        self._line_start = self._offset = start
        self._reset_buffers()
        # Persist now so a lock handover resumes here instead of re-applying start_at.
        await self._store_offset()
        return handle

    @staticmethod
    def _decode(raw: bytes) -> str:
        return raw.decode("utf-8", errors="replace").rstrip("\r")

    def _enqueue(self, text: str, size: int, error: str | None = None) -> None:
        self._queue.append(QueuedLine(text, self._line_start, size, error))
        self._line_start += size

    def _split_lines(self, chunk: bytes) -> None:
        """Split into complete lines; the unterminated tail waits for its newline."""
        pos = 0
        while pos < len(chunk):
            newline = chunk.find(b"\n", pos)
            end = len(chunk) if newline < 0 else newline
            if self._skip_prefix is not None:
                self._skip_size += end - pos + (newline >= 0)
                if newline >= 0:
                    self._enqueue(self._skip_prefix, self._skip_size, "line_too_long")
                    self._skip_prefix = None
                pos = end + 1
                continue
            self._partial += chunk[pos:end]
            pos = end + 1
            if len(self._partial) > MAX_LINE_BYTES:
                # Over-long line: keep only a prefix for the DLQ and skip to the next newline.
                self._skip_prefix = self._decode(self._partial[:MAX_LINE_BYTES])
                self._skip_size = len(self._partial) + (newline >= 0)
                self._partial = b""
                if newline >= 0:
                    self._enqueue(self._skip_prefix, self._skip_size, "line_too_long")
                    self._skip_prefix = None
            elif newline >= 0:
                self._enqueue(self._decode(self._partial), len(self._partial) + 1)
                self._partial = b""

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
                        key = f"{self.source.id}:{self._inode}:{item.start}"
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

    async def _load_offset(self) -> tuple[int, int] | None:
        """Stored (inode, offset); a corrupt value counts as none."""
        raw = await self._redis.get(self._offset_key)
        if raw is None:
            return None
        try:
            inode, _, offset = raw.decode().partition(":")
            return int(inode), int(offset)
        except ValueError:
            log.warning("log_tail_offset_corrupt", extra={"source_id": self.source.id})
            return None

    async def _store_offset(self) -> None:
        await self._redis.set(self._offset_key, f"{self._inode}:{self._offset}")
