"""Compile rule conditions once, then evaluate them against event contexts.

Semantics: a missing field never matches, except `exists` with value false. `ne` on a
missing field is therefore False too. `not` simply inverts its child, so `not` over a
missing-field leaf is True. Comparisons never raise; incomparable types are False.

Coercion: real numbers and strictly numeric strings (`-12`, `3.5`, `1e5`; no `inf`, `1_000`
or spaces) compare numerically. When BOTH sides are numeric strings they also compare
numerically, so `"1.0" eq "1"` is true. bool is never a number. Inside `all`, children are
reordered cheapest first at compile time; leaves are pure, so the result is unchanged.
"""

from __future__ import annotations

import fnmatch
import operator
import re
import re._constants as _sre_constants
import re._parser as _sre_parser
from collections.abc import Callable, Iterator, Mapping
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
from .temporal import severity_gte_predicate, time_between_predicate

CompiledCondition = Callable[[Mapping[str, Any]], bool]
_Predicate = Callable[[Any], bool]

_LAYER_KEYS = frozenset({"normalized", "alert"})
MAX_PATTERN_LENGTH = 512
MAX_SUBJECT_LENGTH = 8192
_NUMERIC = re.compile(r"-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?")
_is_numeric_text = _NUMERIC.fullmatch
_GLOB_SPECIAL = re.compile(r"[*?\[]")
_ORDERING = {
    ConditionOperator.gt: operator.gt,
    ConditionOperator.gte: operator.ge,
    ConditionOperator.lt: operator.lt,
    ConditionOperator.lte: operator.le,
}
# Rough evaluation cost used to order `all` children: cheap checks first.
_COST = {
    ConditionOperator.exists: 0,
    ConditionOperator.eq: 1,
    ConditionOperator.ne: 1,
    ConditionOperator.in_: 1,
    ConditionOperator.gt: 2,
    ConditionOperator.gte: 2,
    ConditionOperator.lt: 2,
    ConditionOperator.lte: 2,
    ConditionOperator.glob: 3,
    ConditionOperator.regex: 4,
    ConditionOperator.severity_gte: 2,
    ConditionOperator.time_between: 3,
}


def _to_number(value: Any) -> float | int | None:
    """Number view of a value: real numbers and strictly numeric strings; bool is not one."""
    kind = type(value)
    if kind is int or kind is float:
        return value
    if kind is str and _is_numeric_text(value):
        return float(value)
    return None


def _equals(actual: Any, expected: Any) -> bool:
    """Equality with numeric coercion; bool only equals bool."""
    if isinstance(actual, bool) or isinstance(expected, bool):
        return isinstance(actual, bool) and isinstance(expected, bool) and actual == expected
    left, right = _to_number(actual), _to_number(expected)
    if left is not None and right is not None:
        return left == right
    if left is not None or right is not None:
        # one side numeric, the other not: a plain string equal to a numeric string is
        # impossible here (both would be numeric), so they differ.
        return False
    try:
        return bool(actual == expected)
    except Exception:  # noqa: BLE001 - exotic __eq__ must not break the hot path
        return False


def _compare_predicate(op: ConditionOperator, expected: Any) -> _Predicate:
    """eq/ne/gt/gte/lt/lte with the rule-side value parsed once."""
    is_equality = op in (ConditionOperator.eq, ConditionOperator.ne)
    compare = operator.eq if is_equality else _ORDERING[op]
    threshold = None if isinstance(expected, bool) else _to_number(expected)
    expected_is_text = isinstance(expected, str)

    def slow(actual: Any) -> bool:
        if is_equality:
            return _equals(actual, expected)
        if isinstance(actual, str) and expected_is_text:
            return bool(compare(actual, expected))  # both non-numeric text: lexical order
        return False

    if threshold is None:
        if op is ConditionOperator.ne:
            return lambda actual: not _equals(actual, expected)
        return slow

    negate = op is ConditionOperator.ne

    def numeric(actual: Any) -> bool:
        kind = type(actual)
        if kind is int or kind is float:
            return bool(compare(actual, threshold)) is not negate
        if kind is str and _is_numeric_text(actual):
            return bool(compare(float(actual), threshold)) is not negate
        # Non-numeric actual against a numeric rule value: never equal, never ordered.
        return negate

    return numeric


def _in_predicate(expected: Any) -> _Predicate:
    if not isinstance(expected, list):
        raise ValueError("operator 'in' needs a list value")
    members: frozenset[Any] | None = None
    if not any(isinstance(item, bool) for item in expected):
        try:
            members = frozenset(expected)
        except TypeError:
            members = None
    has_numeric_member = any(_to_number(item) is not None for item in expected)

    def linear(actual: Any) -> bool:
        return any(_equals(actual, item) for item in expected)

    if members is None or has_numeric_member:
        return linear

    def predicate(actual: Any) -> bool:
        # No numeric members, so the set is authoritative for hashable, non-bool actuals.
        if type(actual) is bool:
            return False
        try:
            return actual in members
        except TypeError:
            return linear(actual)

    return predicate


_REPEAT_OPS = (_sre_constants.MAX_REPEAT, _sre_constants.MIN_REPEAT)
_OP_TYPE = type(_sre_constants.MAX_REPEAT)
_UNBOUNDED = _sre_constants.MAXREPEAT
# Bounded nesting such as (\d{1,3}\.){3} is fine; this caps outer_max * inner_max.
_MAX_NESTED_PRODUCT = 64


def _walk(node: Any) -> Iterator[tuple[Any, Any]]:
    """Yield every (op, argument) node below `node`, however deeply nested."""
    if isinstance(node, _sre_parser.SubPattern):
        node = node.data
    if not isinstance(node, list | tuple):
        return
    if len(node) == 2 and isinstance(node[0], _OP_TYPE):
        yield node[0], node[1]
    for item in node:
        if isinstance(item, tuple | list | _sre_parser.SubPattern):
            yield from _walk(item)


def _literal_text(branch: Any) -> str | None:
    """The branch as plain text when it is only literal characters, else None."""
    items = branch.data if isinstance(branch, _sre_parser.SubPattern) else branch
    if not all(op is _sre_constants.LITERAL for op, _ in items):
        return None
    return "".join(chr(argument) for _, argument in items)


def _has_overlapping_branch(body: Any) -> bool:
    """True when an alternation in `body` can match empty, or has identical or prefix branches.

    The parser factors a common prefix out, so `(a|aa)` arrives as `a` + `(|a)`; empty branches
    are therefore the signal for those. Distinct literals like POST|PUT and class or category
    branches are linear in CPython and stay allowed.
    """
    for op, argument in _walk(body):
        if op is not _sre_constants.BRANCH:
            continue
        texts: list[str] = []
        for branch in argument[1]:
            items = branch.data if isinstance(branch, _sre_parser.SubPattern) else branch
            if not items:
                return True
            text = _literal_text(branch)
            if text is not None:
                texts.append(text)
        for index, first in enumerate(texts):
            if any(first.startswith(other) for other in texts[:index]) or any(
                other.startswith(first) for other in texts[:index]
            ):
                return True
    return False


def check_pattern_safety(pattern: str) -> None:
    r"""Reject patterns that can backtrack catastrophically; raises ValueError.

    Refused: over-long patterns, backreferences, nested repetition unless both bounds are
    small (`(a+)+`, `(a+){1,50}`, `(a{1,100}){1,100}`), and alternation under repetition with
    identical, prefix-related or empty alternatives (`(a|a)+`, `(a|aa)+`).
    The parse tree comes from the private `re._parser` because the public API cannot expose
    quantifier structure; the stdlib `re` has no timeout, so the shape must be rejected up front.
    """
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise ValueError(f"regex longer than {MAX_PATTERN_LENGTH} characters")
    try:
        tree = _sre_parser.parse(pattern)
    except (re.error, OverflowError, RecursionError) as exc:
        raise ValueError(f"invalid regex: {exc}") from exc
    for op, argument in _walk(tree):
        if op is _sre_constants.GROUPREF or op is _sre_constants.GROUPREF_EXISTS:
            raise ValueError("regex has backreferences, which can backtrack exponentially")
        if op not in _REPEAT_OPS:
            continue
        _, outer_max, body = argument
        if outer_max <= 1:
            continue
        for inner_op, inner in _walk(body):
            if inner_op not in _REPEAT_OPS or inner[1] <= 1:
                continue
            inner_max = inner[1]
            is_bounded = outer_max != _UNBOUNDED and inner_max != _UNBOUNDED
            if not is_bounded or outer_max * inner_max > _MAX_NESTED_PRODUCT:
                raise ValueError(
                    "regex has nested quantifiers that can backtrack exponentially; "
                    "bound them tightly, e.g. {1,8}"
                )
        if _has_overlapping_branch(body):
            raise ValueError("regex has overlapping alternation under repetition, e.g. (a|a)+")


def _compile_pattern(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern)
    except (re.error, OverflowError, RecursionError) as exc:
        raise ValueError(f"invalid pattern {pattern!r}: {exc}") from exc


def _glob_predicate(expected: Any) -> _Predicate:
    if not isinstance(expected, str):
        raise ValueError("operator 'glob' needs a string value")
    if len(expected) > MAX_PATTERN_LENGTH:
        raise ValueError(f"glob longer than {MAX_PATTERN_LENGTH} characters")
    prefix = expected[:-1]
    if expected.endswith("*") and not _GLOB_SPECIAL.search(prefix):
        # "type.*" is by far the most common glob; startswith skips the regex engine.
        return lambda actual: isinstance(actual, str) and actual.startswith(prefix)
    glob_regex = _compile_pattern(fnmatch.translate(expected))  # case-sensitive
    match = glob_regex.match
    limit = MAX_SUBJECT_LENGTH
    return lambda actual: isinstance(actual, str) and match(actual[:limit]) is not None


def _regex_predicate(expected: Any) -> _Predicate:
    if not isinstance(expected, str):
        raise ValueError("operator 'regex' needs a string value")
    check_pattern_safety(expected)
    search = _compile_pattern(expected).search
    limit = MAX_SUBJECT_LENGTH
    return lambda actual: isinstance(actual, str) and search(actual[:limit]) is not None


def build_predicate(op: ConditionOperator, expected: Any) -> _Predicate:
    if op is ConditionOperator.in_:
        return _in_predicate(expected)
    if op is ConditionOperator.glob:
        return _glob_predicate(expected)
    if op is ConditionOperator.regex:
        return _regex_predicate(expected)
    if op is ConditionOperator.severity_gte:
        return severity_gte_predicate(expected)
    if op is ConditionOperator.time_between:
        return time_between_predicate(expected)
    return _compare_predicate(op, expected)


def _compile_leaf(leaf: ConditionLeaf) -> CompiledCondition:
    segments = split_field_path(leaf.field)
    if leaf.op is ConditionOperator.exists:
        wants_present = True if leaf.value is None else bool(leaf.value)
        return lambda context: (lookup_segments(context, segments) is not MISSING) is wants_present
    predicate = build_predicate(leaf.op, leaf.value)

    def matches_general(context: Mapping[str, Any]) -> bool:
        value = lookup_segments(context, segments)
        return value is not MISSING and predicate(value)

    if len(segments) > 2:
        return matches_general
    # Only `normalized` and `alert` are layered, so any other first segment can be read from
    # the raw payload directly, skipping the Python-level `__missing__` hop. Plain-mapping
    # contexts (no `.payload`) and unusual shapes fall back to the general lookup.
    is_payload_path = segments[0] not in _LAYER_KEYS
    if len(segments) == 1:
        key = segments[0]

        def matches_top_level(context: Mapping[str, Any]) -> bool:
            try:
                return predicate((context.payload if is_payload_path else context)[key])  # type: ignore[attr-defined]
            except (KeyError, TypeError, AttributeError):
                return matches_general(context)

        return matches_top_level

    first, second = segments

    def matches_two_levels(context: Mapping[str, Any]) -> bool:
        try:
            root = context.payload if is_payload_path else context  # type: ignore[attr-defined]
            return predicate(root[first][second])
        except (KeyError, TypeError, IndexError, AttributeError):
            return matches_general(context)

    return matches_two_levels


def _compile_with_cost(condition: Condition) -> tuple[CompiledCondition, int]:
    if isinstance(condition, ConditionLeaf):
        return _compile_leaf(condition), _COST[condition.op]
    if isinstance(condition, ConditionNot):
        child, cost = _compile_with_cost(condition.not_)
        return (lambda context: not child(context)), cost
    if isinstance(condition, ConditionAll):
        parts = sorted((_compile_with_cost(item) for item in condition.all), key=lambda p: p[1])
        all_children = tuple(part[0] for part in parts)

        def matches_all(context: Mapping[str, Any]) -> bool:
            for child in all_children:  # plain loop: cheaper than a generator on the hot path
                if not child(context):
                    return False
            return True

        return matches_all, sum(part[1] for part in parts)
    if isinstance(condition, ConditionAny):
        any_parts = [_compile_with_cost(item) for item in condition.any]
        any_children = tuple(part[0] for part in any_parts)

        def matches_any(context: Mapping[str, Any]) -> bool:
            for child in any_children:
                if child(context):
                    return True
            return False

        return matches_any, sum(part[1] for part in any_parts)
    raise TypeError(f"unsupported condition: {type(condition).__name__}")


def compile_condition(condition: Condition) -> CompiledCondition:
    """Compile a condition tree into a `matches(context) -> bool` callable.

    Regexes and globs are compiled here, so callers compile once per rule version.
    Raises ValueError for a malformed leaf: bad or unsafe regex/glob (over 512 characters,
    nested unbounded quantifiers) or a non-list `in` value.
    """
    return _compile_with_cost(condition)[0]


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
