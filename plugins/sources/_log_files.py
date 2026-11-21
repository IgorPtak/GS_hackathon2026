"""File helpers and line splitting for the log-tail source (blocking I/O; call via to_thread)."""

import os
import re
from typing import Any, BinaryIO, NamedTuple

import orjson
from alerting_contracts.config import SourceConfig
from alerting_core.logging import get_logger
from alerting_core.rules.conditions import MAX_SUBJECT_LENGTH, check_pattern_safety

MAX_LINE_BYTES = 1 << 20
HEAD_BYTES = 64

FileIdentity = tuple[int, int]  # (st_ino, st_dev)


log = get_logger(__name__)


class QueuedLine(NamedTuple):
    """One complete line read from the file, waiting to be appended."""

    text: str
    start: int  # byte offset of the line start in the file
    size: int  # bytes consumed, including the newline when there was one
    error: str | None = None  # set for lines that go straight to the DLQ


def open_file(path: str) -> tuple[BinaryIO, FileIdentity, int, bytes] | None:
    """Open `path`; returns (handle, identity, size, head bytes) or None when it is missing."""
    try:
        handle = open(path, "rb")  # noqa: SIM115  (kept open across polls)
    except OSError:
        return None
    stat = os.fstat(handle.fileno())
    return (
        handle,
        (stat.st_ino, stat.st_dev),
        stat.st_size,
        os.pread(handle.fileno(), HEAD_BYTES, 0),
    )


def poll_file(handle: BinaryIO, path: str) -> tuple[int, int, FileIdentity | None, bytes]:
    """Return (open file size, our read position, identity now at `path` or None, head bytes).

    The head lets the caller notice a truncate-and-regrow that never looked smaller.
    """
    try:
        stat = os.stat(path)
        path_identity: FileIdentity | None = (stat.st_ino, stat.st_dev)
    except OSError:
        path_identity = None
    fd = handle.fileno()
    return os.fstat(fd).st_size, handle.tell(), path_identity, os.pread(fd, HEAD_BYTES, 0)


def decode_line(raw: bytes) -> str:
    """Decode leniently: a bad byte must not stop the tail."""
    return raw.decode("utf-8", errors="replace").rstrip("\r")


class LineSplitter:
    """Turns raw chunks into complete lines; an unterminated tail waits for its newline."""

    def __init__(self) -> None:
        self.partial = b""
        self.line_start = 0  # file offset where the current line began
        self._skip_prefix: str | None = None  # set while discarding an over-long line
        self._skip_size = 0

    def reset(self, start: int = 0) -> None:
        """Forget buffered bytes and continue from file offset `start`."""
        self.partial = b""
        self.line_start = start
        self._skip_prefix = None
        self._skip_size = 0

    def take_partial(self) -> QueuedLine | None:
        """Hand over the unterminated last line (used when the file is rotated away)."""
        if not self.partial:
            return None
        line = QueuedLine(decode_line(self.partial), self.line_start, len(self.partial))
        self.partial = b""
        return line

    def split(self, chunk: bytes) -> list[QueuedLine]:
        """Return the lines completed by `chunk`."""
        lines: list[QueuedLine] = []
        pos = 0
        while pos < len(chunk):
            newline = chunk.find(b"\n", pos)
            end = len(chunk) if newline < 0 else newline
            has_newline = newline >= 0
            if self._skip_prefix is not None:
                self._skip_size += end - pos + has_newline
                if has_newline:
                    self._emit(lines, self._skip_prefix, self._skip_size, "line_too_long")
                    self._skip_prefix = None
                pos = end + 1
                continue
            self.partial += chunk[pos:end]
            pos = end + 1
            if len(self.partial) > MAX_LINE_BYTES:
                # Over-long line: keep only a prefix for the DLQ and skip to the next newline.
                self._skip_prefix = decode_line(self.partial[:MAX_LINE_BYTES])
                self._skip_size = len(self.partial) + has_newline
                self.partial = b""
                if has_newline:
                    self._emit(lines, self._skip_prefix, self._skip_size, "line_too_long")
                    self._skip_prefix = None
            elif has_newline:
                self._emit(lines, decode_line(self.partial), len(self.partial) + 1)
                self.partial = b""
        return lines

    def _emit(
        self, lines: list[QueuedLine], text: str, size: int, error: str | None = None
    ) -> None:
        lines.append(QueuedLine(text, self.line_start, size, error))
        self.line_start += size


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
    if len(line) > MAX_SUBJECT_LENGTH:
        # Bounds regex work per line; longer lines go to the DLQ like non-matching ones.
        raise LineParseError(f"line longer than {MAX_SUBJECT_LENGTH} characters for line_pattern")
    match = pattern.match(line)
    if match is None:
        raise LineParseError("line does not match line_pattern")
    groups = {key: value for key, value in match.groupdict().items() if value is not None}
    return {**groups, "raw_line": line}


# Renew/release only while we still own the lock, so a stalled owner cannot touch a successor's.
RENEW_SCRIPT = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('PEXPIRE', KEYS[1], ARGV[2]) else return 0 end"
)
RELEASE_SCRIPT = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('DEL', KEYS[1]) else return 0 end"
)


def compile_pattern(source: SourceConfig) -> re.Pattern[str] | None:
    """Compile `settings.line_pattern`; an invalid or unsafe one is logged, lines go to the DLQ."""
    raw = source.settings.get("line_pattern")
    if not raw:
        return None
    try:
        check_pattern_safety(raw)
        return re.compile(raw)
    except (re.error, ValueError) as error:
        log.error("log_tail_pattern_invalid", extra={"source_id": source.id, "error": str(error)})
        return None
