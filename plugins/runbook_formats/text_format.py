"""Free-text runbooks: fallback is one text step holding the whole text."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from alerting_contracts.config import ActionConfig, ApprovalPolicy
from alerting_contracts.runbooks import RunbookFormat, RunbookStep, StepKind

from plugins.runbook_formats.base import RunbookFormatPlugin
from plugins.runbook_formats.registry import register_runbook_format

# Only a human turns on automation or many retries; an LLM proposal never gets them.
LLM_MAX_ATTEMPTS = 3
_URL_OR_HOST = re.compile(r"^\s*(?:[a-z][a-z0-9+.-]*://|[\w.-]+:\d{1,5}(?:[/?#]|\s*$))", re.I)

LlmNormalizer = Callable[[str, Mapping[str, ActionConfig]], list[RunbookStep]]


def _harden_action_step(step: RunbookStep, action: ActionConfig) -> RunbookStep:
    """Automation off, attempts clamped, URL-like params dropped, approval never loosened."""
    params = {k: v for k, v in step.params.items() if not _URL_OR_HOST.match(v)}
    dropped = sorted(set(step.params) - set(params))
    text = step.text
    if dropped:
        text = f"{text} (dropped params that looked like URLs or hosts: {', '.join(dropped)})"
    update: dict[str, object] = {
        "is_automatic": False,
        "max_attempts": min(step.max_attempts, LLM_MAX_ATTEMPTS),
        "params": params,
        "text": text,
    }
    if action.approval is ApprovalPolicy.required:
        update["approval"] = ApprovalPolicy.required
    return step.model_copy(update=update)


def validate_llm_steps(
    steps: list[RunbookStep], actions: Mapping[str, ActionConfig]
) -> list[RunbookStep]:
    """Make an LLM proposal safe; pure. Returns [] when nothing usable is left (caller falls back).

    - unknown action id, or a check/action step without an action -> text step (text kept);
    - known action with missing required params -> step is KEPT with its action: the runner
      refuses to run it and the UI shows it, so an operator can fix the params;
    - action with approval: required -> approval forced to required;
    - is_automatic is always off (only a human turns automation on); max_attempts <= 3;
    - param values that look like a URL or host:port are dropped, and the step text says so;
    - steps with blank text are dropped; indexes are re-numbered 0..n-1 in the given order.
    """
    result: list[RunbookStep] = []
    for step in steps:
        if not step.text.strip():
            continue
        action = actions.get(step.action) if step.action else None
        if action is None:
            step = step.model_copy(
                update={
                    "kind": StepKind.text,
                    "action": None,
                    "params": {},
                    "approval": None,
                    "is_automatic": False,
                    "max_attempts": 1,
                }
            )
        else:
            step = _harden_action_step(step, action)
        result.append(step)
    return [step.model_copy(update={"index": i}) for i, step in enumerate(result)]


RISKY_ACTION_WORDS = ("restart", "escalate", "retry")


def _is_risky(action: ActionConfig) -> bool:
    """Restart, escalate and retry actions never run without a human, whatever their config says."""
    name = f"{action.id} {action.type}".lower()
    return any(word in name for word in RISKY_ACTION_WORDS)


def _as_manual_step(step: RunbookStep) -> RunbookStep:
    return step.model_copy(
        update={
            "kind": StepKind.text,
            "action": None,
            "params": {},
            "approval": None,
            "is_automatic": False,
        }
    )


def guard_llm_steps(
    steps: list[RunbookStep], actions: Mapping[str, ActionConfig]
) -> list[RunbookStep]:
    """Strict guard for LLM proposals: `validate_llm_steps` plus the safety rules; pure.

    - an action step missing a required param becomes a manual text step (a human does it);
    - approval is forced to required unless the action's policy is `none` and it is not risky
      (restart/escalate/retry); a forced step is never automatic.
    """
    result: list[RunbookStep] = []
    for step in validate_llm_steps(steps, actions):
        action = actions.get(step.action) if step.action else None
        if action is not None:
            given = {name for name, value in step.params.items() if value.strip()}
            required = {name for name, spec in action.params.items() if spec.is_required}
            if not required <= given:
                step = _as_manual_step(step)
            elif action.approval is not ApprovalPolicy.none or _is_risky(action):
                step = step.model_copy(
                    update={"approval": ApprovalPolicy.required, "is_automatic": False}
                )
        result.append(step)
    return result


@register_runbook_format
class TextRunbookFormat(RunbookFormatPlugin):
    format = RunbookFormat.text

    def __init__(self, llm_normalizer: LlmNormalizer | None = None) -> None:
        # Seam for B-09: an LLM normalizer returning steps; None = fallback only.
        self._llm_normalizer = llm_normalizer

    def normalize(self, source: str, actions: Mapping[str, ActionConfig]) -> list[RunbookStep]:
        text = source.strip()
        if not text:
            raise ValueError("runbook text is empty")
        if self._llm_normalizer is not None:
            return self._llm_normalizer(text, actions)
        return [RunbookStep(index=0, kind=StepKind.text, text=text)]
