"""Free-text runbooks: fallback is one text step holding the whole text."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from alerting_contracts.config import ActionConfig, ApprovalPolicy
from alerting_contracts.runbooks import RunbookFormat, RunbookStep, StepKind

from plugins.runbook_formats.base import RunbookFormatPlugin
from plugins.runbook_formats.registry import register_runbook_format

LlmNormalizer = Callable[[str, Mapping[str, ActionConfig]], list[RunbookStep]]


def validate_llm_steps(
    steps: list[RunbookStep], actions: Mapping[str, ActionConfig]
) -> list[RunbookStep]:
    """Make an LLM proposal safe; pure. Returns [] when nothing usable is left (caller falls back).

    - unknown action id, or a check/action step without an action -> text step (text kept);
    - known action with missing required params -> step is KEPT with its action: the runner
      refuses to run it and the UI shows it, so an operator can fix the params;
    - action with approval: required -> approval forced to required and is_automatic off;
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
                }
            )
        elif action.approval is ApprovalPolicy.required:
            step = step.model_copy(
                update={"approval": ApprovalPolicy.required, "is_automatic": False}
            )
        result.append(step)
    return [step.model_copy(update={"index": i}) for i, step in enumerate(result)]


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
