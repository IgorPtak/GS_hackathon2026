"""render_runbook / runbook_step_texts against the settlements WORKFLOW_FAILED fixture."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import yaml
from alerting_contracts.alerts import Alert
from alerting_contracts.config import ActionConfig, ApprovalPolicy, Severity
from alerting_contracts.runbooks import (
    Runbook,
    RunbookFormat,
    RunbookStep,
    RunbookYamlDocument,
    StepKind,
)
from alerting_core.runbooks.rendering import render_runbook, runbook_step_texts

ROOT = Path(__file__).resolve().parents[4]
WF = "wf-settle-20261120-0042"


def _alert(event: dict) -> Alert:
    now = datetime(2026, 11, 20, 10, 15, tzinfo=UTC)
    return Alert(
        id="alert-1",
        rule_id="workflow-failed",
        team="settlements",
        schema_profile_id="settlements",
        source_id="settlements",
        fingerprint="fp",
        severity=Severity.critical,
        title="t",
        first_seen=now,
        last_seen=now,
        last_event=event,
        updated_at=now,
    )


def _actions() -> dict[str, ActionConfig]:
    result = {}
    for path in (ROOT / "config" / "actions").glob("*.yaml"):
        action = ActionConfig.model_validate(yaml.safe_load(path.read_text()))
        result[action.id] = action
    return result


def _runbook(steps: list[RunbookStep] | None = None) -> Runbook:
    source = (ROOT / "config" / "runbooks" / "workflow-failed.yaml").read_text()
    doc = RunbookYamlDocument.model_validate(yaml.safe_load(source))
    return Runbook(
        id=doc.id,
        title=doc.title,
        team=doc.team,
        format=RunbookFormat.yaml,
        source=source,
        steps=steps if steps is not None else doc.steps,
        normalized_by="parser",
    )


def _event() -> dict:
    return json.loads(
        (ROOT / "contracts/fixtures/events/settlements_workflow_failed.json").read_text()
    )


def test_fixture_runbook_renders_text_params_and_metadata() -> None:
    rendered = render_runbook(_runbook(), _alert(_event()), _actions())
    assert rendered.runbook_id == "workflow-failed"
    assert rendered.alert_id == "alert-1"
    assert rendered.format == RunbookFormat.yaml
    assert rendered.source.startswith("id: workflow-failed")
    s0, s1, s2, s3 = rendered.steps
    assert s0.text == "Check health of settlement-engine"
    assert s0.params["url"] == "http://mock-gateway:8090/services/settlement-engine/health"
    assert s0.is_automatic
    assert WF in s1.text and s1.params == {"workflow_id": WF}
    assert s1.run_if == "previous_succeeded" and s1.max_attempts == 2
    assert s2.params == {"workflow_id": WF, "reason": "UPSTREAM_TIMEOUT"}
    assert s2.run_if == "previous_failed"
    assert WF in s3.text
    assert all(step.missing_fields == [] for step in rendered.steps)


def test_approval_from_action_and_step_override_both_directions() -> None:
    steps = [
        RunbookStep(index=0, kind=StepKind.action, text="a", action="retry-workflow"),
        RunbookStep(index=1, kind=StepKind.action, text="b", action="escalate"),
        RunbookStep(
            index=2,
            kind=StepKind.action,
            text="c",
            action="retry-workflow",
            approval=ApprovalPolicy.required,
        ),
        RunbookStep(
            index=3,
            kind=StepKind.action,
            text="d",
            action="escalate",
            approval=ApprovalPolicy.none,
        ),
        RunbookStep(index=4, kind=StepKind.text, text="e"),
    ]
    rendered = render_runbook(_runbook(steps), _alert(_event()), _actions())
    assert [s.requires_approval for s in rendered.steps] == [False, True, True, False, False]


def test_missing_placeholder_listed_and_rendered_empty() -> None:
    event = _event()
    del event["error"]
    rendered = render_runbook(_runbook(), _alert(event), _actions())
    step = rendered.steps[2]
    assert step.params["reason"] == ""
    assert step.missing_fields == ["error.code"]
    assert rendered.steps[1].missing_fields == []


def test_alert_level_keys_available() -> None:
    steps = [RunbookStep(index=0, kind=StepKind.text, text="{{alert.team}} {{alert.id}}")]
    rendered = render_runbook(_runbook(steps), _alert(_event()), _actions())
    assert rendered.steps[0].text == "settlements alert-1"


def test_unknown_action_logged_and_step_kept(caplog) -> None:
    steps = [RunbookStep(index=0, kind=StepKind.action, text="x", action="nope")]
    with caplog.at_level(logging.WARNING):
        rendered = render_runbook(_runbook(steps), _alert(_event()), _actions())
    assert rendered.steps[0].requires_approval is False
    assert rendered.steps[0].action == "nope"
    assert rendered.steps[0].missing_fields == []
    assert "runbook_unknown_action" in caplog.text


def test_runbook_step_texts_numbered_with_approval_marker() -> None:
    rendered = render_runbook(_runbook(), _alert(_event()), _actions())
    lines = runbook_step_texts(rendered)
    assert lines[0] == "1. Check health of settlement-engine"
    assert lines[2] == f"3. Escalate {WF} to the settlements lead (approval required)"
    assert lines[3].startswith("4. Confirm") and "approval" not in lines[3]
