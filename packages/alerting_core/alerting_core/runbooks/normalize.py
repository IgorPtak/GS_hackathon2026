"""Turn a runbook source text into a stored `Runbook` through the format plugins."""

from collections.abc import Mapping
from typing import Literal

from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import Runbook, RunbookFormat

from plugins.runbook_formats import get_runbook_format


def normalize_runbook(
    id: str,
    title: str,
    team: str | None,
    format: RunbookFormat,
    source: str,
    actions: Mapping[str, ActionConfig],
) -> Runbook:
    """Normalize `source`; raises ValidationError/ValueError on bad input.

    yaml and markdown are parsed (`normalized_by="parser"`); text without an LLM is the
    one-step fallback. B-09 adds the LLM path (`normalized_by="llm"`, `llm_model` set).
    """
    format = RunbookFormat(format)
    steps = get_runbook_format(format).normalize(source, actions)
    normalized_by: Literal["parser", "fallback"] = (
        "fallback" if format is RunbookFormat.text else "parser"
    )
    return Runbook(
        id=id,
        title=title,
        team=team,
        format=format,
        source=source,
        steps=steps,
        normalized_by=normalized_by,
        llm_model=None,
    )
