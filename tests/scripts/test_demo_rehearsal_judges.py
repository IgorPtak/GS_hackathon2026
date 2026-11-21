"""Pure-logic unit tests for the `judges_path` rehearsal scene (no live stack)."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alerting_contracts.alerts import Alert
from alerting_contracts.api import SchemaProfileTestResult, SchemaProfileTestSample
from alerting_contracts.common import Severity
from alerting_contracts.config import (
    ActionConfig,
    ApprovalPolicy,
    ConditionAll,
    ConditionLeaf,
    ConditionOperator,
    SchemaProfile,
)
from alerting_contracts.events import NormalizedFields
from alerting_contracts.proposals import SchemaProfileProposal
from alerting_contracts.runbooks import Runbook, RunbookFormat, RunbookStep, StepKind
from alerting_core.runbooks.approval_policy import step_requires_approval

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from demo_rehearsal_helpers import RehearsalError  # noqa: E402
from demo_rehearsal_judges import (  # noqa: E402
    DISCRIMINATOR_FIELD,
    assert_judges_alert,
    assert_normalized_runbook,
    assert_profile_test_matched_sample,
    build_judges_rule,
    build_judges_runbook_write,
    build_judges_samples,
    build_robot_event,
    format_judges_detail,
    judges_discriminator,
    judges_resource_id,
    prepare_proposed_profile,
)


def _known_actions() -> dict[str, ActionConfig]:
    return {
        "http-health-check": ActionConfig(id="http-health-check", type="http_get"),
        "retry-workflow": ActionConfig(id="retry-workflow", type="retry_workflow"),
        "escalate": ActionConfig(id="escalate", type="webhook", approval=ApprovalPolicy.required),
    }


def _sample_runbook() -> Runbook:
    return Runbook(
        id="judges-ab12",
        title="Robot recovery",
        team="platform",
        format=RunbookFormat.text,
        source="check, retry, escalate",
        normalized_by="llm",
        steps=[
            RunbookStep(
                index=0, kind=StepKind.check, text="Check health", action="http-health-check"
            ),
            RunbookStep(
                index=1,
                kind=StepKind.action,
                text="Page on-call manager",
                action="escalate",
                approval=ApprovalPolicy.required,
            ),
        ],
    )


def test_build_judges_samples_uses_fresh_robot_ids_and_stable_discriminator() -> None:
    sample_a, live_a = build_judges_samples("ab12cd34")
    sample_b, live_b = build_judges_samples("ef567890")
    assert sample_a[DISCRIMINATOR_FIELD] == sample_b[DISCRIMINATOR_FIELD] == "warehouse-robot"
    assert sample_a["robot"]["id"] == "bot-ab12cd34-sample"
    assert sample_a["robot"]["id"] != sample_b["robot"]["id"]
    assert sample_a["site"] == "wh-ab12cd34"
    assert sample_a["fault"]["level"] == "FATAL"
    assert [e["fault"]["level"] for e in live_a] == ["FATAL", "WARN", "FATAL"]
    assert {e["robot"]["id"] for e in live_a} == {"bot-ab12cd34-live"}
    assert {e["robot"]["id"] for e in live_b} == {"bot-ef567890-live"}
    assert {e[DISCRIMINATOR_FIELD] for e in live_a} == {"warehouse-robot"}


def test_build_robot_event_preserves_custom_fields() -> None:
    event = build_robot_event("aa11", "bot-42", "WARN", "SENSOR_DRIFT", "2026-11-20T12:00:00Z")
    assert event == {
        DISCRIMINATOR_FIELD: "warehouse-robot",
        "robot": {"id": "bot-42", "bay": "B4"},
        "fault": {"code": "SENSOR_DRIFT", "level": "WARN"},
        "ts": "2026-11-20T12:00:00Z",
        "site": "wh-aa11",
    }


def test_prepare_proposed_profile_forces_id_and_scopes_match() -> None:
    raw = SchemaProfile.model_validate(
        {
            "id": "robot-fault",
            "priority": 10,
            "match": {
                "all": [
                    {"field": "robot.id", "op": "exists", "value": True},
                    {"field": "fault.level", "op": "exists", "value": True},
                ]
            },
            "fields": {"severity": "fault.level", "entity": "robot.id"},
            "fingerprint": ["robot.id"],
        }
    )
    proposal = SchemaProfileProposal(profile=raw, generated_by="llm", model="test-model")
    prepared = prepare_proposed_profile(proposal, "judges-ab12", "warehouse-robot-ab12")
    expected_leaf = ConditionLeaf(
        field=DISCRIMINATOR_FIELD, op=ConditionOperator.eq, value="warehouse-robot-ab12"
    )
    assert prepared.id == "judges-ab12"
    assert isinstance(prepared.match, ConditionAll)
    assert expected_leaf in prepared.match.all


def test_prepare_proposed_profile_wraps_leaf_match() -> None:
    raw = SchemaProfile.model_validate(
        {
            "id": "robot-fault",
            "priority": 10,
            "match": {"field": "robot.id", "op": "exists", "value": True},
            "fields": {"entity": "robot.id"},
            "fingerprint": ["robot.id"],
        }
    )
    prepared = prepare_proposed_profile(
        SchemaProfileProposal(profile=raw, generated_by="heuristic"),
        "judges-1234",
        "warehouse-robot-1234",
    )
    assert prepared.id == "judges-1234"
    assert isinstance(prepared.match, ConditionAll) and len(prepared.match.all) == 2


def test_build_judges_rule_sets_conditions_dedup_route_and_runbook() -> None:
    rule = build_judges_rule()
    assert rule.id == judges_resource_id() == "judges-demo"
    assert rule.team == "platform" and rule.enabled is True and rule.runbook == "judges-demo"
    assert rule.dedup.fingerprint == ["robot.id"]
    assert rule.route.recipients == ["marek"] and rule.route.channels == ["ui", "email"]
    assert isinstance(rule.when, ConditionAll)
    assert rule.when.all == [
        ConditionLeaf(field="fault.level", op=ConditionOperator.eq, value="FATAL"),
        ConditionLeaf(
            field=DISCRIMINATOR_FIELD, op=ConditionOperator.eq, value=judges_discriminator()
        ),
    ]
    assert build_judges_rule(enabled=False).enabled is False


def test_build_judges_runbook_write_uses_text_format() -> None:
    payload = build_judges_runbook_write().model_dump(mode="json")
    assert payload["id"] == "judges-demo" and payload["team"] == "platform"
    assert payload["format"] == "text" and "page" in payload["source"].lower()


def test_assert_profile_test_matched_sample_checks_null_event_id() -> None:
    norm = NormalizedFields(schema_profile_id="judges-ab12", fingerprint="bot-1")
    matched = SchemaProfileTestResult(
        events_scanned=10,
        events_matched=0,
        samples=[SchemaProfileTestSample(event_id=None, normalized=norm)],
    )
    assert_profile_test_matched_sample(matched)
    unmatched = SchemaProfileTestResult(
        events_scanned=10,
        events_matched=1,
        samples=[SchemaProfileTestSample(event_id="evt-1", normalized=norm)],
    )
    with pytest.raises(RehearsalError, match="did not match sample_event"):
        assert_profile_test_matched_sample(unmatched)


def test_step_requires_approval_checks_step_and_action_config() -> None:
    actions = _known_actions()
    explicit = RunbookStep(
        index=0, kind=StepKind.text, text="Page manager", approval=ApprovalPolicy.required
    )
    inherited = RunbookStep(index=1, kind=StepKind.action, text="Escalate", action="escalate")
    unapproved = RunbookStep(index=2, kind=StepKind.check, text="Check", action="http-health-check")
    assert step_requires_approval(explicit, actions) is True
    assert step_requires_approval(inherited, actions) is True
    assert step_requires_approval(unapproved, actions) is False


def test_assert_normalized_runbook_accepts_valid_and_rejects_short_or_unmapped() -> None:
    actions, good = _known_actions(), _sample_runbook()
    assert_normalized_runbook(good, actions)
    with pytest.raises(RehearsalError, match=">= 2"):
        assert_normalized_runbook(good.model_copy(update={"steps": [good.steps[0]]}), actions)
    no_action = good.model_copy(
        update={
            "steps": [
                RunbookStep(index=0, kind=StepKind.text, text="Check health"),
                RunbookStep(
                    index=1, kind=StepKind.text, text="Page", approval=ApprovalPolicy.required
                ),
            ]
        }
    )
    with pytest.raises(RehearsalError, match="mapped no known action"):
        assert_normalized_runbook(no_action, actions)


def test_assert_normalized_runbook_rejects_ungated_escalation() -> None:
    actions, good = _known_actions(), _sample_runbook()
    ungated = good.model_copy(
        update={
            "steps": [
                good.steps[0],
                RunbookStep(
                    index=1, kind=StepKind.text, text="Page manager", approval=ApprovalPolicy.none
                ),
            ]
        }
    )
    with pytest.raises(RehearsalError, match="does not require approval"):
        assert_normalized_runbook(ungated, actions)


def test_assert_judges_alert_validates_profile_rule_runbook_and_count() -> None:
    now = datetime.now(UTC)
    alert = Alert(
        id="01934567-89ab-7def-8000-000000000001",
        rule_id="judges-ab12",
        team="platform",
        schema_profile_id="judges-ab12",
        source_id="generic-webhook",
        fingerprint="bot-ab12-live",
        severity=Severity.critical,
        title="Robot fault",
        count=2,
        first_seen=now,
        last_seen=now,
        runbook_id="judges-ab12",
        last_event={},
        updated_at=now,
    )
    assert_judges_alert(alert, "judges-ab12")
    with pytest.raises(RehearsalError, match="schema_profile_id"):
        assert_judges_alert(
            alert.model_copy(update={"schema_profile_id": "generic"}), "judges-ab12"
        )
    with pytest.raises(RehearsalError, match="runbook_id"):
        assert_judges_alert(alert.model_copy(update={"runbook_id": None}), "judges-ab12")
    with pytest.raises(RehearsalError, match="count=1"):
        assert_judges_alert(alert.model_copy(update={"count": 1}), "judges-ab12")


def test_format_judges_detail_formats_cleanly_with_optional_warnings() -> None:
    clean = format_judges_detail("judges-ab12", "llm", 3, "llm", 2)
    assert clean == (
        "profile judges-ab12 (llm), rule saved, "
        "runbook 3 steps (llm, escalate needs approval), alert count=2"
    )
    warned = format_judges_detail(
        "judges-ab12", "heuristic", 2, "llm", 2, warnings=["profile generated by heuristic"]
    )
    assert "warning: profile generated by heuristic" in warned
