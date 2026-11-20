"""LogTailRunner tests against a real Redis (DB 8, flushed per test) and tmp files."""

import asyncio
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import orjson
import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from alerting_contracts.config import SourceConfig
from alerting_contracts.events import EventEnvelope

from plugins.sources import log_tail
from plugins.sources.log_tail import LogTailRunner

FIXTURES = Path(__file__).resolve().parents[3] / "contracts" / "fixtures" / "events"
PATTERN = (
    r"^(?P<timestamp>\S+) (?P<level>[A-Z]+) (?P<service>\S+) instrument=(?P<instrument>\S+) "
    r'feed=(?P<feed>\S+) age_ms=(?P<age_ms>\d+) msg="(?P<msg>[^"]*)"$'
)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[aioredis.Redis]:
    conn = aioredis.Redis.from_url("redis://localhost:6379/8")
    try:
        await conn.flushdb()
    except aioredis.ConnectionError:
        pytest.skip("Redis not reachable on localhost:6379")
    yield conn
    await conn.flushdb()
    await conn.aclose()


@pytest.fixture(autouse=True)
def fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_tail, "POLL_SECONDS", 0.02)


def make_source(path: Path, **settings: object) -> SourceConfig:
    base = {"path": str(path), "line_format": "regex", "line_pattern": PATTERN, "start_at": "end"}
    return SourceConfig(id="pricing-log", type="log_tail", settings={**base, **settings})


class Tail:
    """Runs a runner in the background and collects what it appends."""

    def __init__(self, source: SourceConfig, redis: aioredis.Redis) -> None:
        self.envelopes: list[EventEnvelope] = []
        self.runner = LogTailRunner(source, redis, self._append)
        self.task: asyncio.Task[None] | None = None

    async def _append(self, envelopes: list[EventEnvelope]) -> None:
        self.envelopes.extend(envelopes)

    def start(self) -> None:
        self.task = asyncio.create_task(self.runner.run())

    async def stop(self) -> None:
        assert self.task is not None
        self.task.cancel()
        await asyncio.gather(self.task, return_exceptions=True)

    async def wait_for(self, count: int) -> None:
        for _ in range(200):
            if len(self.envelopes) >= count:
                return
            await asyncio.sleep(0.02)
        raise AssertionError(f"expected {count} events, got {len(self.envelopes)}")


async def test_fixture_lines_match_expected_payload(client: aioredis.Redis, tmp_path: Path) -> None:
    path = tmp_path / "app.log"
    path.write_text("")
    tail = Tail(make_source(path), client)
    tail.start()
    await asyncio.sleep(0.1)
    with path.open("a") as handle:
        handle.write((FIXTURES / "pricing_engine.log").read_text())
    await tail.wait_for(4)
    await tail.stop()
    expected = json.loads((FIXTURES / "pricing_price_stale.json").read_text())
    assert tail.envelopes[0].payload == expected
    assert tail.envelopes[0].source_type == "log_tail"
    assert tail.envelopes[0].idempotency_key == f"pricing-log:{path.stat().st_ino}:0"


async def test_partial_line_waits_for_newline(client: aioredis.Redis, tmp_path: Path) -> None:
    path = tmp_path / "app.log"
    path.write_text("")
    tail = Tail(make_source(path, line_format="json"), client)
    tail.start()
    await asyncio.sleep(0.1)
    with path.open("a") as handle:
        handle.write('{"a": ')
        handle.flush()
        await asyncio.sleep(0.15)
        assert tail.envelopes == []
        handle.write("1}\n")
    await tail.wait_for(1)
    await tail.stop()
    assert tail.envelopes[0].payload == {"a": 1, "raw_line": '{"a": 1}'}


async def test_survives_rotation(client: aioredis.Redis, tmp_path: Path) -> None:
    path = tmp_path / "app.log"
    path.write_text("")
    tail = Tail(make_source(path, line_format="json"), client)
    tail.start()
    await asyncio.sleep(0.1)
    with path.open("a") as handle:
        handle.write('{"n": 1}\n')
    await tail.wait_for(1)
    os.rename(path, tmp_path / "app.log.1")
    path.write_text('{"n": 2}\n')
    await tail.wait_for(2)
    await tail.stop()
    assert [e.payload["n"] for e in tail.envelopes] == [1, 2]


async def test_survives_truncation(client: aioredis.Redis, tmp_path: Path) -> None:
    path = tmp_path / "app.log"
    path.write_text("")
    tail = Tail(make_source(path, line_format="json"), client)
    tail.start()
    await asyncio.sleep(0.1)
    with path.open("a") as handle:
        handle.write('{"n": 1}\n{"n": 2}\n')
    await tail.wait_for(2)
    path.write_text('{"n": 3}\n')
    await tail.wait_for(3)
    await tail.stop()
    assert tail.envelopes[-1].payload["n"] == 3


async def test_missing_file_is_waited_for(client: aioredis.Redis, tmp_path: Path) -> None:
    path = tmp_path / "later.log"
    tail = Tail(make_source(path, line_format="json", start_at="beginning"), client)
    tail.start()
    await asyncio.sleep(0.1)
    path.write_text('{"n": 1}\n')
    await tail.wait_for(1)
    await tail.stop()


async def test_parse_failure_goes_to_dlq_with_raw_line(
    client: aioredis.Redis, tmp_path: Path
) -> None:
    path = tmp_path / "app.log"
    path.write_text("not a pricing line\n")
    tail = Tail(make_source(path, start_at="beginning"), client)
    tail.start()
    for _ in range(100):
        if await client.xlen("events-dlq"):
            break
        await asyncio.sleep(0.02)
    await tail.stop()
    ((_, fields),) = await client.xrange("events-dlq")
    assert orjson.loads(fields[b"envelope"])["payload"] == {"raw_line": "not a pricing line"}
    assert fields[b"attempts"] == b"1"
    assert fields[b"error"]
    assert tail.envelopes == []


async def test_restart_resumes_from_stored_offset(client: aioredis.Redis, tmp_path: Path) -> None:
    path = tmp_path / "app.log"
    path.write_text('{"n": 1}\n{"n": 2}\n')
    first = Tail(make_source(path, line_format="json", start_at="beginning"), client)
    first.start()
    await first.wait_for(2)
    await first.stop()
    with path.open("a") as handle:
        handle.write('{"n": 3}\n')
    second = Tail(make_source(path, line_format="json", start_at="beginning"), client)
    second.start()
    await second.wait_for(1)
    await asyncio.sleep(0.1)
    await second.stop()
    assert [e.payload["n"] for e in second.envelopes] == [3]


async def test_only_one_runner_holds_the_lock(client: aioredis.Redis, tmp_path: Path) -> None:
    path = tmp_path / "app.log"
    path.write_text('{"n": 1}\n')
    owner = Tail(make_source(path, line_format="json", start_at="beginning"), client)
    other = Tail(make_source(path, line_format="json", start_at="beginning"), client)
    owner.start()
    await owner.wait_for(1)
    other.start()
    await asyncio.sleep(0.2)
    assert other.envelopes == []
    await owner.stop()  # releases the lock
    assert await client.get("log-tail-lock:pricing-log") is None
    await other.stop()


async def test_file_created_after_start_is_read_from_beginning(
    client: aioredis.Redis, tmp_path: Path
) -> None:
    path = tmp_path / "later.log"
    tail = Tail(make_source(path, line_format="json", start_at="end"), client)
    tail.start()
    await asyncio.sleep(0.1)
    path.write_text('{"n": 1}\n{"n": 2}\n')
    await tail.wait_for(2)
    await tail.stop()


async def test_start_at_end_skips_existing_content_and_stores_offset(
    client: aioredis.Redis, tmp_path: Path
) -> None:
    path = tmp_path / "app.log"
    path.write_text('{"n": 0}\n')
    tail = Tail(make_source(path, line_format="json", start_at="end"), client)
    tail.start()
    await asyncio.sleep(0.15)
    stored = (await client.get("log-tail-offset:pricing-log")).decode()
    await tail.stop()
    assert stored == f"{path.stat().st_ino}:{path.stat().st_size}"
    assert tail.envelopes == []


async def test_run_survives_errors_and_retries(
    client: aioredis.Redis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log_tail, "ERROR_RETRY_SECONDS", 0.05)
    path = tmp_path / "app.log"
    path.write_text('{"n": 1}\n')
    tail = Tail(make_source(path, line_format="json", start_at="beginning"), client)
    original = tail.runner._open
    calls = 0

    async def flaky_open() -> object:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        return await original()

    monkeypatch.setattr(tail.runner, "_open", flaky_open)
    tail.start()
    await tail.wait_for(1)
    await tail.stop()
    assert calls >= 2


async def test_corrupt_offset_is_treated_as_missing(client: aioredis.Redis, tmp_path: Path) -> None:
    await client.set("log-tail-offset:pricing-log", "garbage")
    path = tmp_path / "app.log"
    path.write_text('{"n": 1}\n')
    tail = Tail(make_source(path, line_format="json", start_at="beginning"), client)
    tail.start()
    await tail.wait_for(1)
    await tail.stop()


async def test_over_long_line_goes_to_dlq_and_is_skipped(
    client: aioredis.Redis, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log_tail, "MAX_LINE_BYTES", 50)
    monkeypatch.setattr(log_tail, "READ_BYTES", 16)
    path = tmp_path / "app.log"
    path.write_text("x" * 200 + '\n{"n": 2}\n')
    tail = Tail(make_source(path, line_format="json", start_at="beginning"), client)
    tail.start()
    await tail.wait_for(1)
    await tail.stop()
    ((_, fields),) = await client.xrange("events-dlq")
    assert fields[b"error"] == b"line_too_long"
    prefix = orjson.loads(fields[b"envelope"])["payload"]["raw_line"]
    assert prefix == "x" * 50
    assert [e.payload["n"] for e in tail.envelopes] == [2]


async def test_truncation_is_detected_before_reading(
    client: aioredis.Redis, tmp_path: Path
) -> None:
    path = tmp_path / "app.log"
    path.write_text("")
    tail = Tail(make_source(path, line_format="json"), client)
    tail.start()
    await asyncio.sleep(0.1)
    with path.open("a") as handle:
        handle.write('{"n": 1}\n' * 3)
    await tail.wait_for(3)
    # New content shorter than the old position, written in one go: found without waiting for EOF.
    path.write_text('{"n": 9}\n')
    await tail.wait_for(4)
    await tail.stop()
    assert tail.envelopes[-1].payload["n"] == 9


async def test_rotation_flushes_unterminated_last_line(
    client: aioredis.Redis, tmp_path: Path
) -> None:
    path = tmp_path / "app.log"
    path.write_text("")
    tail = Tail(make_source(path, line_format="json"), client)
    tail.start()
    await asyncio.sleep(0.1)
    with path.open("a") as handle:
        handle.write('{"n": 1}\n{"n": 2}')
    await tail.wait_for(1)
    os.rename(path, tmp_path / "app.log.1")
    path.write_text('{"n": 3}\n')
    await tail.wait_for(3)
    await tail.stop()
    assert [e.payload["n"] for e in tail.envelopes] == [1, 2, 3]


async def test_envelopes_carry_deterministic_idempotency_keys(
    client: aioredis.Redis, tmp_path: Path
) -> None:
    path = tmp_path / "app.log"
    first_line = '{"n": 1}\n'
    path.write_text(first_line + '{"n": 2}\n')
    tail = Tail(make_source(path, line_format="json", start_at="beginning"), client)
    tail.start()
    await tail.wait_for(2)
    await tail.stop()
    inode = path.stat().st_ino
    keys = [e.idempotency_key for e in tail.envelopes]
    assert keys == [f"pricing-log:{inode}:0", f"pricing-log:{inode}:{len(first_line)}"]
