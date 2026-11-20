"""Compile rule conditions once, then evaluate them against event contexts.

Semantics: a missing field never matches, except `exists` with value false. `ne` on a
missing field is therefore False too. `not` simply inverts its child, so `not` over a
missing-field leaf is True. Comparisons never raise; incomparable types are False.
"""

from __future__ import annotations

import fnmatch
import re
from collections.abc import Callable, Mapping
from typing import Any

from alerting_contracts.config import (
    Condition,
    ConditionAll,
    ConditionAny,
    ConditionLeaf,
    ConditionNot,
    ConditionOperator,
)

from .field_paths import MISSING, lookup_segments, split_field_path

CompiledCondition = Callable[[Mapping[str, Any]], bool]
_Predicate = Callable[[Any], bool]


def _to_number(value: Any) -> float | int | None:
    """Number view of a value: real numbers and numeric strings; bool is not a number."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _is_real_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _equals(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return isinstance(actual, bool) and isinstance(expected, bool) and actual == expected
    if _is_real_number(actual) or _is_real_number(expected):
        left, right = _to_number(actual), _to_number(expected)
        return left is not None and right is not None and left == right
    try:
        return bool(actual == expected)
    except Exception:  # noqa: BLE001 - exotic __eq__ must not break the hot path
        return False


def _ordered(actual: Any, expected: Any) -> tuple[Any, Any] | None:
    """Pair of comparable values, or None when the types are incomparable."""
    if _is_real_number(actual) or _is_real_number(expected):
        left, right = _to_number(actual), _to_number(expected)
        return None if left is None or right is None else (left, right)
    if isinstance(actual, str) and isinstance(expected, str):
        return actual, expected
    return None


def _ordering_predicate(op: ConditionOperator, expected: Any) -> _Predicate:
    compare: Callable[[Any, Any], bool] = {
        ConditionOperator.gt: lambda a, b: a > b,
        ConditionOperator.gte: lambda a, b: a >= b,
        ConditionOperator.lt: lambda a, b: a < b,
        ConditionOperator.lte: lambda a, b: a <= b,
    }[op]
    # Fast path: numeric threshold (the common case) with an already-numeric field.
    threshold = expected if _is_real_number(expected) else None

    def predicate(actual: Any) -> bool:
        if threshold is not None and type(actual) in (int, float):
            return compare(actual, threshold)
        pair = _ordered(actual, expected)
        return pair is not None and compare(*pair)

    return predicate


def _in_predicate(expected: Any) -> _Predicate:
    if not isinstance(expected, list):
        raise ValueError("operator 'in' needs a list value")
    try:
        members: frozenset[Any] | None = frozenset(expected)
    except TypeError:
        members = None

    def predicate(actual: Any) -> bool:
        if members is not None and not isinstance(actual, bool):
            try:
                if actual in members:
                    return True
            except TypeError:
                pass
        return any(_equals(actual, item) for item in expected)

    return predicate


def _build_predicate(op: ConditionOperator, expected: Any) -> _Predicate:
    if op is ConditionOperator.eq:
        return lambda actual: _equals(actual, expected)
    if op is ConditionOperator.ne:
        return lambda actual: not _equals(actual, expected)
    if op is ConditionOperator.in_:
        return _in_predicate(expected)
    if op is ConditionOperator.glob:
        if not isinstance(expected, str):
            raise ValueError("operator 'glob' needs a string value")
        glob_regex = re.compile(fnmatch.translate(expected))  # case-sensitive like fnmatchcase
        return lambda actual: isinstance(actual, str) and glob_regex.match(actual) is not None
    if op is ConditionOperator.regex:
        if not isinstance(expected, str):
            raise ValueError("operator 'regex' needs a string value")
        pattern = re.compile(expected)
        return lambda actual: isinstance(actual, str) and pattern.search(actual) is not None
    return _ordering_predicate(op, expected)


def _compile_leaf(leaf: ConditionLeaf) -> CompiledCondition:
    segments = split_field_path(leaf.field)
    if leaf.op is ConditionOperator.exists:
        wants_present = True if leaf.value is None else bool(leaf.value)
        return lambda context: (lookup_segments(context, segments) is not MISSING) is wants_present
    predicate = _build_predicate(leaf.op, leaf.value)
    if len(segments) == 1:
        key = segments[0]

        def matches_top_level(context: Mapping[str, Any]) -> bool:
            try:
                return predicate(context[key])
            except KeyError:
                return False

        return matches_top_level

    def matches(context: Mapping[str, Any]) -> bool:
        value = lookup_segments(context, segments)
        return value is not MISSING and predicate(value)

    return matches


def compile_condition(condition: Condition) -> CompiledCondition:
    """Compile a condition tree into a `matches(context) -> bool` callable.

    Regexes and globs are compiled here, so callers compile once per rule version.
    Raises ValueError for a malformed leaf (bad regex, non-list `in` value).
    """
    if isinstance(condition, ConditionLeaf):
        return _compile_leaf(condition)
    if isinstance(condition, ConditionNot):
        child = compile_condition(condition.not_)
        return lambda context: not child(context)
    if isinstance(condition, ConditionAll):
        all_children = tuple(compile_condition(item) for item in condition.all)

        def matches_all(context: Mapping[str, Any]) -> bool:
            for child in all_children:  # plain loop: cheaper than a generator on the hot path
                if not child(context):
                    return False
            return True

        return matches_all
    if isinstance(condition, ConditionAny):
        any_children = tuple(compile_condition(item) for item in condition.any)

        def matches_any(context: Mapping[str, Any]) -> bool:
            for child in any_children:
                if child(context):
                    return True
            return False

        return matches_any
    raise TypeError(f"unsupported condition: {type(condition).__name__}")


# Explicit registry: id(condition) -> (condition, compiled). The condition is kept alive so
# its id cannot be reused; bounded so hot-reloaded rule versions do not accumulate.
_CACHE_LIMIT = 1024
_compiled_by_id: dict[int, tuple[Condition, CompiledCondition]] = {}


def evaluate_condition(condition: Condition, context: Mapping[str, Any]) -> bool:
    """Convenience: compile (cached per condition object) and evaluate once."""
    cached = _compiled_by_id.get(id(condition))
    if cached is None or cached[0] is not condition:
        if len(_compiled_by_id) >= _CACHE_LIMIT:
            _compiled_by_id.clear()
        cached = (condition, compile_condition(condition))
        _compiled_by_id[id(condition)] = cached
    return cached[1](context)
