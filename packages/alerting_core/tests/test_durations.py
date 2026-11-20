import pytest
from alerting_core.durations import parse_duration, parse_duration_ms


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("500ms", 0.5), ("60s", 60.0), ("5m", 300.0), ("1h", 3600.0), ("1d", 86400.0), ("0s", 0.0)],
)
def test_parse_duration_returns_seconds(text: str, seconds: float) -> None:
    assert parse_duration(text) == seconds


def test_parse_duration_ms_returns_whole_milliseconds() -> None:
    assert parse_duration_ms("5m") == 300_000
    assert parse_duration_ms("250ms") == 250


@pytest.mark.parametrize("text", ["", "5", "5 m", "-5s", "1.5h", "5w", "m5"])
def test_parse_duration_rejects_invalid_text(text: str) -> None:
    with pytest.raises(ValueError):
        parse_duration(text)
