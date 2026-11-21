"""Rule regex and glob conditions cannot stall the event loop."""

from __future__ import annotations

import time
from typing import Any

import pytest
from alerting_contracts.config import Condition
from alerting_core.rules import build_context, compile_condition
from pydantic import TypeAdapter

_adapter: TypeAdapter[Condition] = TypeAdapter(Condition)


def leaf(op: str, value: Any) -> Condition:
    return _adapter.validate_python({"field": "f", "op": op, "value": value})


def check(spec: Condition, subject: str) -> bool:
    return compile_condition(spec)(build_context({"f": subject}, {}))


@pytest.mark.parametrize(
    "pattern",
    [
        "(a{1,100}){1,100}",
        "(a+){1,50}",
        "(a|a)+",
        "(a|ab)+$",
        "(a|aa)+$",
        r"(a)\1+",
        r"(?P<x>a+)(?P=x)",
    ],
)
# `(\w|\d)+` and `(a|A)*b` are not listed: CPython folds them into one character class,
# which is linear, so they are harmless.
def test_dangerous_regex_shapes_are_rejected(pattern: str) -> None:
    with pytest.raises(ValueError):
        compile_condition(leaf("regex", pattern))


@pytest.mark.parametrize(
    "pattern", [r"^(\d{1,3}\.){3}\d{1,3}$", "(?:foo|bar)+", "(ab){1,3}c+", r"^(?:GET|POST) /\S+$"]
)
def test_legitimate_nesting_and_disjoint_alternation_still_compile(pattern: str) -> None:
    compile_condition(leaf("regex", pattern))


def test_glob_is_fast_on_long_subject_and_pattern_length_is_capped() -> None:
    spec = leaf("glob", "*a*a*a*a*a*a*a*a*b")
    started = time.perf_counter()
    assert not check(spec, "a" * 8192)
    assert time.perf_counter() - started < 0.05
    with pytest.raises(ValueError, match="longer"):
        compile_condition(leaf("glob", "a?" * 300))


def test_glob_subject_is_truncated() -> None:
    spec = leaf("glob", "*needle")
    assert check(spec, "x" * 8185 + "needle")
    assert not check(spec, "x" * 8192 + "needle")
