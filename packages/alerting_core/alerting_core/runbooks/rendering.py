"""Render a normalized runbook against an alert. Pure: no I/O."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from alerting_contracts.alerts import Alert
from alerting_contracts.config import ActionConfig, ApprovalPolicy
from alerting_contracts.runbooks import (
    RenderedRunbook,
    RenderedRunbookStep,
    Runbook,
    RunbookStep,
    StepKind,
)

from ..rules.field_paths import build_context
from ..templating import render_template

logger = logging.getLogger("alerting_core.runbooks")


def _alert_context(alert: Alert) -> Mapping[str, Any]:
    """Same layering as presentation: raw last_event, `normalized.*`, `alert.*`."""
    alert_fields = alert.model_dump(mode="json", exclude={"last_event"})
    return build_context(alert.last_event, {}, alert_fields)


def _requires_approval(step: RunbookStep, actions: Mapping[str, ActionConfig]) -> bool:
    if step.approval is not None:
        return step.approval == ApprovalPolicy.required
    if step.action is None or step.kind == StepKind.text:
        return False
    action = actions.get(step.action)
    if action is None:
        logger.warning(
            json.dumps(
                {"event": "runbook_unknown_action", "action": step.action, "step": step.index}
            )
        )
        return False
    return action.approval == ApprovalPolicy.required


def render_runbook(
    runbook: Runbook, alert: Alert, actions: Mapping[str, ActionConfig]
) -> RenderedRunbook:
    """Fill every step's text and params from the alert and resolve approval."""
    context = _alert_context(alert)
    steps: list[RenderedRunbookStep] = []
    for step in runbook.steps:
        text = render_template(step.text, context)
        missing = list(text.missing_fields)
        params: dict[str, str] = {}
        for key, template in step.params.items():
            rendered = render_template(template, context)
            params[key] = rendered.text
            missing.extend(rendered.missing_fields)
        steps.append(
            RenderedRunbookStep(
                index=step.index,
                kind=step.kind,
                text=text.text,
                action=step.action,
                params=params,
                requires_approval=_requires_approval(step, actions),
                is_automatic=step.is_automatic,
                run_if=step.run_if,
                max_attempts=step.max_attempts,
                missing_fields=missing,
            )
        )
    return RenderedRunbook(
        runbook_id=runbook.id,
        alert_id=alert.id,
        title=runbook.title,
        format=runbook.format,
        source=runbook.source,
        steps=steps,
    )


def runbook_step_texts(rendered: RenderedRunbook) -> list[str]:
    """Numbered lines for NotificationContent.runbook_steps."""
    return [
        f"{position}. {step.text}" + (" (approval required)" if step.requires_approval else "")
        for position, step in enumerate(rendered.steps, start=1)
    ]
