"""Parse the human durations used in YAML config ("500ms", "60s", "5m", "1h", "1d")."""

import re

_DURATION_PATTERN = re.compile(r"^([0-9]+)(ms|s|m|h|d)$")
_SECONDS_PER_UNIT = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": 86400.0}


def parse_duration(text: str) -> float:
    """Return seconds; raise ValueError for anything the contract `Duration` pattern rejects."""
    match = _DURATION_PATTERN.match(text.strip())
    if match is None:
        raise ValueError(f"invalid duration {text!r}; expected e.g. 500ms, 60s, 5m, 1h, 1d")
    amount, unit = match.groups()
    return int(amount) * _SECONDS_PER_UNIT[unit]


def parse_duration_ms(text: str) -> int:
    """Duration in whole milliseconds, for Redis TTLs (PX) and sorted-set scores."""
    return round(parse_duration(text) * 1000)
