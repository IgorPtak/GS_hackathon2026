"""LLM draft of a fix proposal (B-24): prompt building and the model call; nothing is persisted.

The draft is only a proposal. The caller still runs the same validation the create endpoint uses
and the human reviews the prefilled form before sending it.
"""

import json
from collections.abc import Callable, Mapping
from pathlib import Path

from alerting_contracts.alerts import Alert
from alerting_contracts.api import ConfigValidationError
from alerting_contracts.config import ActionConfig, Rule
from alerting_contracts.proposals import FixProposalCreate
from alerting_contracts.runbooks import Runbook
from alerting_core.config.store import canonical_yaml
from alerting_core.llm import LlmClient, LlmError, LlmOutputInvalidError, redact_secrets
from alerting_core.logging import get_logger

from plugins.runbook_formats.text_format import validate_llm_steps

log = get_logger(__name__)

PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "packages/alerting_core/alerting_core/llm/prompts/fix_proposal.md"
)
DRAFT_ACTOR_ID = "llm"


def build_system_prompt(actions: Mapping[str, ActionConfig]) -> str:
    """The fix_proposal.md prompt with the available action ids."""
    listing = "\n".join(f"- {a.id}: {a.description or a.type}" for a in actions.values())
    return PROMPT_PATH.read_text(encoding="utf-8").replace("<<ACTIONS>>", listing or "(none)")


def build_user_prompt(alert: Alert, rule: Rule | None, runbook: Runbook | None) -> str:
    """Alert, its rule YAML and runbook steps as text; secrets are redacted before leaving."""
    alert_view = {
        "title": alert.title,
        "severity": alert.severity,
        "count": alert.count,
        "rule_id": alert.rule_id,
        "runbook_id": alert.runbook_id,
        "fields": [f.model_dump(mode="json") for f in alert.fields],
        "last_event": alert.last_event,
    }
    parts = [
        "Alert:\n" + json.dumps(alert_view, indent=2, default=str),
        "Current rule (YAML):\n" + (canonical_yaml(rule) if rule is not None else "(not found)"),
    ]
    if runbook is not None:
        steps = [s.model_dump(mode="json", exclude_defaults=True) for s in runbook.steps]
        parts.append(f"Runbook {runbook.id} steps:\n" + json.dumps(steps, indent=2))
    else:
        parts.append("The alert has no runbook.")
    # Everything above is outside data: fenced so the system prompt can call it untrusted.
    data = "\n\n".join(parts).replace("</untrusted_input>", "<\\/untrusted_input>")
    # Redacted here as well as in LlmClient.generate so the guarantee does not depend on the client.
    return redact_secrets(
        f"<untrusted_input>\n{data}\n</untrusted_input>\n\nDraft one fix proposal."
    )


class DraftUnavailableError(Exception):
    """No usable LLM (missing client, unreachable, host not allowed)."""


class DraftInvalidError(Exception):
    """The model answer failed validation; carries dot-path details when there are any."""

    def __init__(self, message: str, details: list[ConfigValidationError] | None = None) -> None:
        super().__init__(message)
        self.details = details or []


def _harden_draft_step(
    draft: FixProposalCreate, actions: Mapping[str, ActionConfig]
) -> FixProposalCreate:
    """An LLM step gets the same hardening as LLM runbook steps (no automation, safe params)."""
    step = draft.proposed_runbook_step
    if step is None:
        return draft
    hardened = validate_llm_steps([step], actions)
    if not hardened:
        return draft.model_copy(update={"proposed_runbook_step": None})
    return draft.model_copy(
        update={"proposed_runbook_step": hardened[0].model_copy(update={"index": step.index})}
    )


async def draft_fix_proposal(
    client: LlmClient | None,
    alert: Alert,
    rule: Rule | None,
    runbook: Runbook | None,
    actions: Mapping[str, ActionConfig],
    validate: Callable[
        [Alert, FixProposalCreate, Rule | None, Mapping[str, ActionConfig]],
        list[ConfigValidationError],
    ],
) -> FixProposalCreate:
    """Ask the model for one proposal and check it with `validate` (same as the create route).

    Raises DraftUnavailableError or DraftInvalidError. Nothing is written anywhere.
    """
    if client is None:
        raise DraftUnavailableError("LLM is not configured")
    try:
        answer = await client.generate(
            build_user_prompt(alert, rule, runbook),
            FixProposalCreate,
            system=build_system_prompt(actions),
        )
    except LlmOutputInvalidError as error:
        raise DraftInvalidError(str(error)) from error
    except LlmError as error:
        raise DraftUnavailableError(str(error)) from error
    assert isinstance(answer, FixProposalCreate)
    answer = _harden_draft_step(answer, actions)
    errors = validate(alert, answer, rule, actions)
    if errors:
        raise DraftInvalidError("LLM draft failed validation", errors)
    log.info("fix_proposal_drafted", extra={"alert_id": alert.id, "kind": answer.kind.value})
    return answer.model_copy(
        update={"proposed_by": answer.proposed_by.model_copy(update={"id": DRAFT_ACTOR_ID})}
    )
