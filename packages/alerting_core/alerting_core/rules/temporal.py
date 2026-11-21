"""Predicates for `severity_gte` and `time_between`, built once per rule version."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alerting_contracts.common import SEVERITY_ORDER, Severity

_Predicate = Callable[[Any], bool]

_ALIASES = {
    "debug": Severity.debug,
    "trace": Severity.debug,
    "info": Severity.info,
    "warn": Severity.warning,
    "warning": Severity.warning,
    "err": Severity.error,
    "error": Severity.error,
    "crit": Severity.critical,
    "critical": Severity.critical,
    "fatal": Severity.critical,
}
_RANGE = re.compile(r"^([01][0-9]|2[0-3]):([0-5][0-9])-([01][0-9]|2[0-3]):([0-5][0-9])$")
# Epoch values above this are milliseconds (1e11 s is year 5138; 1e11 ms is 1973).
_EPOCH_MS_THRESHOLD = 1e11


def severity_rank(value: Any) -> int | None:
    """Rank of a severity name or alias (case-insensitive); None when unknown."""
    if not isinstance(value, str):
        return None
    severity = _ALIASES.get(value.strip().lower())
    return None if severity is None else SEVERITY_ORDER[severity]


def severity_gte_predicate(expected: Any) -> _Predicate:
    """True when the field's severity ranks at or above `expected`; unknown values never match."""
    threshold = severity_rank(expected)
    if threshold is None:
        raise ValueError(
            f"unknown severity {expected!r}; use debug, info, warning, error or critical"
        )

    def predicate(actual: Any) -> bool:
        rank = severity_rank(actual)
        return rank is not None and rank >= threshold

    return predicate


def parse_time_window(expected: Any) -> tuple[time, time, ZoneInfo | None]:
    """Parse a `time_between` value into (start, end, zone); zone None means UTC."""
    zone_name: Any = None
    text = expected
    if isinstance(expected, dict):
        extra = set(expected) - {"range", "timezone"}
        if extra:
            raise ValueError(f"unknown keys {sorted(extra)} in time_between value")
        text, zone_name = expected.get("range"), expected.get("timezone")
    if not isinstance(text, str) or (match := _RANGE.match(text)) is None:
        raise ValueError("time_between needs a range like '08:00-20:00'")
    zone: ZoneInfo | None = None
    if zone_name is not None:
        try:
            zone = ZoneInfo(str(zone_name))
        except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
            raise ValueError(f"unknown timezone {zone_name!r}") from exc
    start = time(int(match[1]), int(match[2]))
    end = time(int(match[3]), int(match[4]))
    return start, end, zone


def _to_datetime(value: Any) -> datetime | None:
    """Datetime view of an ISO-8601 string, epoch seconds/ms or datetime; naive means UTC."""
    kind = type(value)
    if kind is datetime:
        moment = value
    elif kind is int or kind is float:
        seconds = value / 1000 if abs(value) >= _EPOCH_MS_THRESHOLD else value
        try:
            return datetime.fromtimestamp(seconds, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    elif kind is str:
        try:
            moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def time_between_predicate(expected: Any) -> _Predicate:
    """True when local time of day is in [start, end); end < start wraps midnight."""
    start, end, parsed_zone = parse_time_window(expected)
    zone = parsed_zone or UTC
    is_wrapping = end < start

    def predicate(actual: Any) -> bool:
        moment = _to_datetime(actual)
        if moment is None:
            return False
        local = moment.astimezone(zone).time().replace(tzinfo=None)
        if is_wrapping:
            return local >= start or local < end
        return start <= local < end

    return predicate
