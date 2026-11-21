from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfoNotFoundError

import pytest
from alerting_core.routing import _is_within


def test_missing_tz_database_falls_back_to_utc(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_zone(key: str) -> object:
        raise ZoneInfoNotFoundError(key)

    monkeypatch.setattr("alerting_core.routing.ZoneInfo", no_zone)
    morning = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    night = datetime(2026, 6, 1, 23, 0, tzinfo=UTC)
    assert _is_within("08:00-20:00", morning, "Nope/Zone", "r", "a")
    assert not _is_within("08:00-20:00", night, "Europe/Warsaw", "r", "a")
