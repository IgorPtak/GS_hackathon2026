"""Stream lag collector: XINFO GROUPS parsing and gauge updates."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from alerting_core.metrics import STREAM_LAG, parse_group_lags, render_metrics, update_stream_lag
from redis.exceptions import ResponseError


def test_parse_group_lags_uses_lag_field() -> None:
    groups = [{"name": b"processors", "pending": 3, "lag": 40}]
    assert parse_group_lags(groups) == {"processors": 40}


def test_parse_group_lags_falls_back_to_pending_when_lag_is_nil() -> None:
    groups = [{"name": "processors", "pending": 7, "lag": None}, {b"name": b"x", b"pending": 1}]
    assert parse_group_lags(groups) == {"processors": 7, "x": 1}


async def test_update_stream_lag_sets_gauge_and_tolerates_missing_stream() -> None:
    async def xinfo(stream: str) -> list[dict[str, object]]:
        if stream == "events":
            return [{"name": b"processors", "pending": 2, "lag": None}]
        raise ResponseError("no such key")

    redis = AsyncMock()
    redis.xinfo_groups.side_effect = xinfo
    await update_stream_lag(redis)
    assert STREAM_LAG.labels("events", "processors")._value.get() == 2
    assert STREAM_LAG.labels("deliveries", "delivery-workers")._value.get() == 0


def test_render_metrics_aggregates_when_multiprocess_dir_is_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
    body, _ = render_metrics()  # no worker files yet: must not raise
    assert b"events_ingested_total" not in body
