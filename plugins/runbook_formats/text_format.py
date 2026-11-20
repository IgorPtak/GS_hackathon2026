"""Free-text runbooks: fallback is one text step holding the whole text."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import RunbookFormat, RunbookStep, StepKind

from plugins.runbook_formats.base import RunbookFormatPlugin
from plugins.runbook_formats.registry import register_runbook_format

LlmNormalizer = Callable[[str, Mapping[str, ActionConfig]], list[RunbookStep]]


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
