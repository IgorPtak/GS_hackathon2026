"""Report invalid rules with dot-path locations instead of silently skipping them."""

from __future__ import annotations

from alerting_contracts.api import ConfigValidationError
from alerting_contracts.config import (
    Condition,
    ConditionAll,
    ConditionAny,
    ConditionLeaf,
    ConditionNot,
    ConditionOperator,
    Rule,
)

from .conditions import build_predicate


def _walk(condition: Condition, path: str, errors: list[ConfigValidationError]) -> None:
    if isinstance(condition, ConditionLeaf):
        if condition.op is ConditionOperator.exists:
            return
        try:
            build_predicate(condition.op, condition.value)
        except ValueError as error:
            errors.append(ConfigValidationError(path=f"{path}.value", message=str(error)))
    elif isinstance(condition, ConditionNot):
        _walk(condition.not_, f"{path}.not", errors)
    elif isinstance(condition, ConditionAll):
        for index, child in enumerate(condition.all):
            _walk(child, f"{path}.all[{index}]", errors)
    elif isinstance(condition, ConditionAny):
        for index, child in enumerate(condition.any):
            _walk(child, f"{path}.any[{index}]", errors)


def validate_rule(rule: Rule) -> list[ConfigValidationError]:
    """Every problem that would stop `rule.when` from compiling, e.g. path `when.all[1].value`.

    Uses the same predicate builders as evaluation, so a rule that validates also compiles.
    """
    errors: list[ConfigValidationError] = []
    _walk(rule.when, "when", errors)
    return errors
