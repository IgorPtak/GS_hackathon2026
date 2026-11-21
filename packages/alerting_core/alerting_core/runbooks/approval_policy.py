"""The one place that decides whether a runbook step needs a human approval.

A step may tighten the policy of its action but never loosen it.
"""

from __future__ import annotations

from collections.abc import Mapping

from alerting_contracts.config import ActionConfig, ApprovalPolicy
from alerting_contracts.runbooks import RunbookStep


class StepPolicyError(ValueError):
    """A runbook step breaks the action policy; carries (dot path, message) pairs for a 422."""

    def __init__(self, problems: list[tuple[str, str]]) -> None:
        super().__init__("; ".join(f"{path}: {message}" for path, message in problems))
        self.problems = problems


def resolve_requires_approval(
    step_approval: ApprovalPolicy | None, action_approval: ApprovalPolicy | None
) -> bool:
    """Action required or step required -> True; otherwise False (step `none` never loosens)."""
    if action_approval is ApprovalPolicy.required:
        return True
    return step_approval is ApprovalPolicy.required


def step_requires_approval(step: RunbookStep, actions: Mapping[str, ActionConfig]) -> bool:
    """Effective approval of a stored step against the current action configs."""
    action = actions.get(step.action) if step.action else None
    return resolve_requires_approval(step.approval, action.approval if action else None)


def tighten_steps(
    steps: list[RunbookStep], actions: Mapping[str, ActionConfig]
) -> list[RunbookStep]:
    """Store `approval: required` on every step whose action requires it; pure."""
    return [
        step.model_copy(update={"approval": ApprovalPolicy.required})
        if step.approval is not ApprovalPolicy.required and step_requires_approval(step, actions)
        else step
        for step in steps
    ]


def check_steps(
    steps: list[RunbookStep], actions: Mapping[str, ActionConfig], path: str = "steps"
) -> list[tuple[str, str]]:
    """Problems that must be a 422 on save: an action id that does not exist."""
    return [
        (f"{path}.{position}.action", f"unknown action {step.action!r}")
        for position, step in enumerate(steps)
        if step.action is not None and step.action not in actions
    ]
