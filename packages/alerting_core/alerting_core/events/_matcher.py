"""Minimal condition matcher for schema profiles.

Replaced by alerting_core.rules.conditions.evaluate_condition once A-08 lands; `_matches` is the
only function the rest of the package calls, so the swap is a one-line change.
"""

from collections.abc import Mapping
from fnmatch import fnmatchcase
from typing import Any

from alerting_contracts.config import (
    ConditionAll,
    ConditionAny,
    ConditionLeaf,
    ConditionNot,
    ConditionOperator,
)

from ._paths import MISSING, get_path


def _matches_leaf(leaf: ConditionLeaf, payload: Mapping[str, Any]) -> bool:
    actual = get_path(payload, leaf.field)
    op = leaf.op
    if op is ConditionOperator.exists:
        return (actual is not MISSING) == bool(leaf.value if leaf.value is not None else True)
    if actual is MISSING:
        return False
    if op is ConditionOperator.eq:
        return actual == leaf.value
    if op is ConditionOperator.ne:
        return actual != leaf.value
    if op is ConditionOperator.in_:
        return isinstance(leaf.value, list) and actual in leaf.value
    if op is ConditionOperator.glob:
        return isinstance(actual, str) and fnmatchcase(actual, str(leaf.value))
    return False  # other operators are not used by schema profiles


def _matches(condition: Any, payload: Mapping[str, Any]) -> bool:
    """True when `payload` satisfies `condition` (all / any / not / leaf)."""
    if isinstance(condition, ConditionLeaf):
        return _matches_leaf(condition, payload)
    if isinstance(condition, ConditionAll):
        return all(_matches(c, payload) for c in condition.all)
    if isinstance(condition, ConditionAny):
        return any(_matches(c, payload) for c in condition.any)
    if isinstance(condition, ConditionNot):
        return not _matches(condition.not_, payload)
    return False
