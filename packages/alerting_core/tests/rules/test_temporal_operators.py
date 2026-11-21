"""severity_gte, time_between and validate_rule."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml
from alerting_contracts.config import Condition, Rule
from alerting_core.rules import build_context, compile_condition, validate_rule
from pydantic import TypeAdapter

ROOT = Path(__file__).resolve().parents[4]
_adapter: TypeAdapter[Condition] = TypeAdapter(Condition)


def check(field: str, op: str, value: Any, payload: dict[str, Any]) -> bool:
    condition = _adapter.validate_python({"field": field, "op": op, "value": value})
    return compile_condition(condition)(build_context(payload, {}))


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ("ERROR", True),
        ("warn", True),
        ("FATAL", True),
        ("info", False),
        ("bogus", False),
        (3, False),
    ],
)
def test_severity_gte_warning(actual: Any, expected: bool) -> None:
    assert check("level", "severity_gte", "WARNING", {"level": actual}) is expected


def test_severity_gte_missing_field_is_false() -> None:
    assert check("level", "severity_gte", "warn", {}) is False


def _window(value: Any, stamp: Any) -> bool:
    return check("ts", "time_between", value, {"ts": stamp})


def test_time_between_bounds_and_wrap_around() -> None:
    assert _window("08:00-20:00", "2026-01-01T08:00:00Z")
    assert not _window("08:00-20:00", "2026-01-01T20:00:00Z")
    assert _window("20:00-08:00", "2026-01-01T23:30:00Z")
    assert _window("20:00-08:00", "2026-01-01T07:59:00Z")
    assert not _window("20:00-08:00", "2026-01-01T12:00:00Z")


def test_time_between_timezone_offset() -> None:
    warsaw = {"range": "08:00-20:00", "timezone": "Europe/Warsaw"}
    assert _window(warsaw, "2026-01-01T07:30:00Z")  # 08:30 local, UTC+1 in winter
    assert not _window(warsaw, "2026-01-01T19:30:00Z")  # 20:30 local
    assert _window(warsaw, "2026-07-01T06:30:00Z")  # 08:30 local, UTC+2 in summer


def test_time_between_epoch_and_datetime_inputs() -> None:
    stamp = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    assert _window("11:00-12:00", int(stamp.timestamp() * 1000))
    assert _window("11:00-12:00", int(stamp.timestamp()))
    assert _window("11:00-12:00", stamp)
    assert not _window("12:00-13:00", int(stamp.timestamp() * 1000))


def test_time_between_unparseable_or_missing_is_false() -> None:
    assert not _window("08:00-20:00", "not a date")
    assert not _window("08:00-20:00", None)
    assert not check("ts", "time_between", "08:00-20:00", {})


def _rule(when: dict[str, Any]) -> Rule:
    return Rule.model_validate(
        {"id": "r", "team": "t", "when": when, "present": {"title": "x"}, "route": {}}
    )


def test_validate_rule_reports_dot_paths() -> None:
    bad_zone = {"range": "08:00-20:00", "timezone": "Mars/Base"}
    rule = _rule(
        {
            "all": [
                {"field": "a", "op": "eq", "value": 1},
                {"field": "b", "op": "regex", "value": "(unclosed"},
                {"any": [{"field": "c", "op": "time_between", "value": bad_zone}]},
                {"field": "d", "op": "in", "value": "x"},
                {"field": "e", "op": "severity_gte", "value": "loud"},
            ]
        }
    )
    errors = validate_rule(rule)
    assert [e.path for e in errors] == [
        "when.all[1].value",
        "when.all[2].any[0].value",
        "when.all[3].value",
        "when.all[4].value",
    ]
    assert "Mars/Base" in errors[2 - 1].message


def test_validate_rule_top_level_leaf_and_valid_rule() -> None:
    assert validate_rule(_rule({"field": "a", "op": "glob", "value": 5}))[0].path == "when.value"
    assert validate_rule(_rule({"field": "a", "op": "severity_gte", "value": "warn"})) == []


def test_validate_rule_accepts_shipped_rules() -> None:
    for path in sorted((ROOT / "config" / "rules").glob("*.yaml")):
        rule = Rule.model_validate(yaml.safe_load(path.read_text()))
        assert validate_rule(rule) == [], path.name
