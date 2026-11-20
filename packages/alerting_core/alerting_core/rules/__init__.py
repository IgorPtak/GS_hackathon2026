"""Rule evaluation: field paths, conditions and a candidate index by `normalized.type`."""

from __future__ import annotations

from collections.abc import Iterable

from alerting_contracts.config import (
    Condition,
    ConditionAll,
    ConditionLeaf,
    ConditionOperator,
)

from .conditions import CompiledCondition, compile_condition, evaluate_condition
from .field_paths import MISSING, EventContext, build_context, resolve_field_path

__all__ = [
    "MISSING",
    "CompiledCondition",
    "EventContext",
    "RuleIndex",
    "build_context",
    "compile_condition",
    "evaluate_condition",
    "index_rules_by_type",
    "resolve_field_path",
]

_TYPE_PATH = "normalized.type"
_CANDIDATE_CACHE_LIMIT = 1024


def _type_constraint(condition: Condition) -> tuple[str, str] | None:
    """`("exact", value)` or `("prefix", value)` when the condition requires a type, else None.

    Only a top-level leaf, or a leaf directly inside a top-level `all`, counts: anything
    nested under `any`/`not` does not restrict the type, so such rules stay candidates.
    """
    leaves = condition.all if isinstance(condition, ConditionAll) else [condition]
    for leaf in leaves:
        if not isinstance(leaf, ConditionLeaf) or leaf.field != _TYPE_PATH:
            continue
        value = leaf.value
        if not isinstance(value, str):
            continue
        if leaf.op is ConditionOperator.eq:
            return "exact", value
        if leaf.op is ConditionOperator.glob and value.endswith("*"):
            prefix = value[:-1]
            if not any(char in prefix for char in "*?["):
                return "prefix", prefix
    return None


class RuleIndex[T]:
    """Candidate rules per `normalized.type`; the full condition is still evaluated."""

    def __init__(self, entries: Iterable[tuple[T, Condition]]) -> None:
        self._exact: dict[str, list[int]] = {}
        self._prefixes: list[tuple[str, int]] = []
        self._unconstrained: list[int] = []
        self._items: list[T] = []
        for position, (item, condition) in enumerate(entries):
            self._items.append(item)
            constraint = _type_constraint(condition)
            if constraint is None:
                self._unconstrained.append(position)
            elif constraint[0] == "exact":
                self._exact.setdefault(constraint[1], []).append(position)
            else:
                self._prefixes.append((constraint[1], position))
        self._cache: dict[str | None, list[T]] = {}

    def candidates(self, event_type: str | None) -> list[T]:
        """Rules that could match an event of this type, in their original order."""
        cached = self._cache.get(event_type)
        if cached is not None:
            return cached
        positions = list(self._unconstrained)
        if event_type is not None:
            positions += self._exact.get(event_type, [])
            positions += [pos for prefix, pos in self._prefixes if event_type.startswith(prefix)]
        found = [self._items[pos] for pos in sorted(positions)]
        if len(self._cache) >= _CANDIDATE_CACHE_LIMIT:
            self._cache.clear()
        self._cache[event_type] = found
        return found


def index_rules_by_type[T](entries: Iterable[tuple[T, Condition]]) -> RuleIndex[T]:
    """Group `(rule, condition)` pairs by an exact or prefix-glob `normalized.type` constraint.

    The processor evaluates only `index.candidates(normalized.type)` per event.
    """
    return RuleIndex(entries)
