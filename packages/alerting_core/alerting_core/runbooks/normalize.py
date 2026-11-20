"""Turn a runbook source text into a stored `Runbook` through the format plugins."""

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import Runbook, RunbookFormat, RunbookStep
from pydantic import BaseModel

from plugins.runbook_formats import get_runbook_format
from plugins.runbook_formats.text_format import validate_llm_steps

from ..llm import LlmClient, LlmError
from ..logging import get_logger

log = get_logger(__name__)

PROMPT_PATH = Path(__file__).resolve().parent.parent / "llm" / "prompts" / "runbook_steps.md"


class StepsResponse(BaseModel):
    """LLM answer: normalized runbook steps."""

    steps: list[RunbookStep]


def build_system_prompt(actions: Mapping[str, ActionConfig]) -> str:
    """The runbook_steps.md prompt with every action id, its params and approval policy."""
    lines = []
    for action in actions.values():
        params = ", ".join(
            f"{name} ({'required' if spec.is_required else 'optional'}"
            + (f": {spec.description}" if spec.description else "")
            + ")"
            for name, spec in action.params.items()
        )
        lines.append(
            f"- {action.id}: {action.description or action.type}; "
            f"approval {action.approval.value}; params: {params or 'none'}"
        )
    listing = "\n".join(lines) or "(none)"
    return PROMPT_PATH.read_text(encoding="utf-8").replace("<<ACTIONS>>", listing)


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


async def normalize_runbook_with_llm(
    id: str,
    title: str,
    team: str | None,
    format: RunbookFormat,
    source: str,
    actions: Mapping[str, ActionConfig],
    client: LlmClient | None,
) -> Runbook:
    """Save-time normalization: free text goes through the LLM once, other formats are parsed.

    The LLM output is a proposal: it is post-validated (`validate_llm_steps`). A missing client,
    any LlmError, or an empty result gives the plain fallback (`normalized_by="fallback"`),
    never an exception. Empty text still raises ValueError like `normalize_runbook`.
    """
    format = RunbookFormat(format)
    if format is not RunbookFormat.text or client is None:
        return normalize_runbook(id, title, team, format, source, actions)
    text = source.strip()
    if not text:
        raise ValueError("runbook text is empty")
    try:
        # redact_secrets is applied inside LlmClient.generate
        answer = await client.generate(text, StepsResponse, system=build_system_prompt(actions))
        assert isinstance(answer, StepsResponse)
        steps = validate_llm_steps(answer.steps, actions)
    except LlmError as error:
        log.warning("runbook_llm_fallback", extra={"runbook": id, "error": str(error)})
        steps = []
    if not steps:
        return normalize_runbook(id, title, team, format, source, actions)
    return Runbook(
        id=id,
        title=title,
        team=team,
        format=format,
        source=source,
        steps=steps,
        normalized_by="llm",
        llm_model=client.model,
    )
