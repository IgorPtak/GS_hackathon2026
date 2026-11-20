"""Pure scoring and aggregation for the runbook LLM eval (no network, no LLM)."""

import math
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class StepScore:
    """How close the actual steps are to the expected ones."""

    step_count_expected: int
    step_count_actual: int
    action_precision: float
    action_recall: float
    approval_accuracy: float
    exact_kind_sequence: bool


def _step_action(step: dict[str, Any]) -> str | None:
    return step.get("action")


def _approval_accuracy(
    expected: Sequence[dict[str, Any]], actual: Sequence[dict[str, Any]]
) -> float:
    """Pair steps with the same action id in order of appearance; share with equal approval."""
    queues: dict[str, list[bool]] = {}
    for step in actual:
        if _step_action(step):
            queues.setdefault(step["action"], []).append(bool(step["requires_approval"]))
    matched = correct = 0
    for step in expected:
        action = _step_action(step)
        if action and queues.get(action):
            matched += 1
            correct += queues[action].pop(0) == bool(step["requires_approval"])
    return correct / matched if matched else 0.0


def score_steps(expected: Sequence[dict[str, Any]], actual: Sequence[dict[str, Any]]) -> StepScore:
    """Compare step dicts with keys kind, action, requires_approval.

    Action precision/recall use the multiset of non-null action ids. With no actions on one side
    the ratio is 1.0 only when the other side has none either (precision) or always (recall).
    Approval accuracy is measured on matched action ids and is 1.0 when nothing could match
    because no actions were expected.
    """
    expected_actions = Counter(a for s in expected if (a := _step_action(s)))
    actual_actions = Counter(a for s in actual if (a := _step_action(s)))
    hits = sum((expected_actions & actual_actions).values())
    total_actual = sum(actual_actions.values())
    total_expected = sum(expected_actions.values())
    precision = hits / total_actual if total_actual else float(total_expected == 0)
    recall = hits / total_expected if total_expected else 1.0
    approval = _approval_accuracy(expected, actual) if total_expected else 1.0
    return StepScore(
        step_count_expected=len(expected),
        step_count_actual=len(actual),
        action_precision=precision,
        action_recall=recall,
        approval_accuracy=approval,
        exact_kind_sequence=[s["kind"] for s in expected] == [s["kind"] for s in actual],
    )


def percentile(values: Sequence[float], fraction: float) -> float:
    """Nearest-rank percentile; 0.0 for no values."""
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def aggregate(scores: Sequence[StepScore | None], latencies: Sequence[float]) -> dict[str, Any]:
    """Per-model summary; `None` in scores marks a failed or fallback run (not scored)."""
    valid = [s for s in scores if s is not None]

    def mean(field: str) -> float:
        return statistics.fmean(float(asdict(s)[field]) for s in valid) if valid else 0.0

    return {
        "runs": len(scores),
        "valid_rate": len(valid) / len(scores) if scores else 0.0,
        "action_precision": mean("action_precision"),
        "action_recall": mean("action_recall"),
        "approval_accuracy": mean("approval_accuracy"),
        "exact_kind_sequence": mean("exact_kind_sequence"),
        "latency_median_s": statistics.median(latencies) if latencies else 0.0,
        "latency_p90_s": percentile(latencies, 0.9),
    }
