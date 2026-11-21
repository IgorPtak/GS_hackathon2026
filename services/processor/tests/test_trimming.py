"""Unit tests for `events` trimming against a fake Redis (no stack needed)."""

import time
from typing import Any

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from services.processor.trimming import (
    EVENTS_RETENTION_MS,
    compute_trim_id,
    parse_stream_id,
    trim_events_once,
)


class FakeRedis:
    """XINFO GROUPS / XPENDING / XTRIM with redis-py's parsed shapes (bytes values)."""

    def __init__(
        self,
        groups: list[dict[str, Any]] | None = None,
        pending: dict[str, dict[str, Any]] | None = None,
        groups_error: Exception | None = None,
        pending_error: Exception | None = None,
    ) -> None:
        self.groups = groups or []
        self.pending = pending or {}
        self.groups_error = groups_error
        self.pending_error = pending_error
        self.trims: list[dict[str, Any]] = []

    async def xinfo_groups(self, stream: str) -> list[dict[str, Any]]:
        if self.groups_error is not None:
            raise self.groups_error
        return self.groups

    async def xpending(self, stream: str, group: bytes) -> dict[str, Any]:
        if self.pending_error is not None:
            raise self.pending_error
        return self.pending.get(
            group.decode(), {"pending": 0, "min": None, "max": None, "consumers": []}
        )

    async def xtrim(self, stream: str, **kwargs: Any) -> int:
        self.trims.append({"stream": stream, **kwargs})
        return 0


def now_ms() -> int:
    return int(time.time() * 1000)


def group(name: str, last_delivered_id: str) -> dict[str, Any]:
    return {"name": name.encode(), "last-delivered-id": last_delivered_id.encode()}


def summary(min_id: str) -> dict[str, Any]:
    return {"pending": 3, "min": min_id.encode(), "max": min_id.encode(), "consumers": []}


def test_parse_stream_id_compares_numerically() -> None:
    assert parse_stream_id("10-0") > parse_stream_id("9-5")
    assert parse_stream_id(b"5-10") > parse_stream_id("5-9")


async def test_no_groups_trims_at_retention_boundary() -> None:
    redis = FakeRedis()
    before = now_ms() - EVENTS_RETENTION_MS
    trim_id = await trim_events_once(redis)  # type: ignore[arg-type]
    after = now_ms() - EVENTS_RETENTION_MS
    assert trim_id is not None
    assert before <= trim_id[0] <= after
    assert redis.trims == [{"stream": "events", "minid": f"{trim_id[0]}-0", "approximate": True}]


async def test_pending_older_than_retention_wins() -> None:
    old = now_ms() - 3 * EVENTS_RETENTION_MS
    redis = FakeRedis(
        groups=[group("processors", f"{now_ms()}-0")],
        pending={"processors": summary(f"{old}-7")},
    )
    assert await trim_events_once(redis) == (old, 7)  # type: ignore[arg-type]
    assert redis.trims[0]["minid"] == f"{old}-7"
    assert redis.trims[0]["approximate"] is True


async def test_group_without_pending_uses_last_delivered_id() -> None:
    lagging = now_ms() - 5 * EVENTS_RETENTION_MS
    redis = FakeRedis(groups=[group("processors", f"{lagging}-2")])
    assert await compute_trim_id(redis, "events", now_ms()) == (lagging, 2)  # type: ignore[arg-type]


async def test_slowest_of_several_groups_is_chosen_numerically() -> None:
    redis = FakeRedis(
        groups=[group("fast", "10000-0"), group("slow", "9999-0")],
        pending={"fast": summary("9000-3")},
    )
    # As strings "9999-0" > "10000-0"; numerically 9000-3 is the lowest frontier.
    assert await compute_trim_id(redis, "events", 10**13) == (9000, 3)  # type: ignore[arg-type]


async def test_fresh_group_at_zero_blocks_trimming() -> None:
    redis = FakeRedis(groups=[group("processors", "0-0")])
    assert await trim_events_once(redis) == (0, 0)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "fake",
    [
        FakeRedis(groups_error=RedisConnectionError("down")),
        FakeRedis(groups_error=ResponseError("WRONGTYPE Operation against a key")),
        FakeRedis(groups=[group("processors", "1-0")], pending_error=RedisConnectionError("x")),
    ],
)
async def test_error_skips_round_and_logs(
    fake: FakeRedis, caplog: pytest.LogCaptureFixture
) -> None:
    assert await trim_events_once(fake) is None  # type: ignore[arg-type]
    assert fake.trims == []
    assert any(record.getMessage() == "events_trim_skipped" for record in caplog.records)


async def test_missing_stream_skips_quietly(caplog: pytest.LogCaptureFixture) -> None:
    redis = FakeRedis(groups_error=ResponseError("no such key"))
    assert await trim_events_once(redis) is None  # type: ignore[arg-type]
    assert redis.trims == []
    assert not any(record.getMessage() == "events_trim_skipped" for record in caplog.records)
