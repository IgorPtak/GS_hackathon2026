"""Delivery content carries the numbered, filled-in runbook steps (pure, no database)."""

from datetime import UTC, datetime

from alerting_contracts.alerts import Alert, DeliveryJob
from alerting_contracts.config import Rule, Severity
from alerting_core.config.registry import ConfigSnapshot
from alerting_core.routing import DeliveryTarget
from alerting_core.runbooks.store import register_runbook_kind

from services.processor.deliveries import build_side_effects

from .conftest import fixture_payload, load_snapshot

WF = "wf-settle-20261120-0042"


def _alert(rule: Rule) -> Alert:
    now = datetime(2026, 11, 20, 10, 15, tzinfo=UTC)
    return Alert(
        id="alert-1",
        rule_id=rule.id,
        team="settlements",
        schema_profile_id="settlements",
        source_id="settlements",
        fingerprint="fp",
        severity=Severity.critical,
        title="t",
        first_seen=now,
        last_seen=now,
        last_event=fixture_payload("settlements_workflow_failed.json"),
        updated_at=now,
    )


def _targets(snapshot: ConfigSnapshot) -> list[DeliveryTarget]:
    channels = list(snapshot.of_kind("channel").values())[:2]
    return [DeliveryTarget(None, channel.id, channel.type) for channel in channels]


def _jobs(rows: list) -> list[DeliveryJob]:
    return [DeliveryJob.model_validate(row[2]) for row in rows if row[0] == "delivery"]


def _build(with_snapshot: bool) -> list[DeliveryJob]:
    register_runbook_kind()  # the processor does this at startup; the loader needs it first
    snapshot = load_snapshot()
    rule = snapshot.of_kind("rule")["settlements-workflow-failed"]
    effects = build_side_effects(
        rule,
        _alert(rule),
        _targets(snapshot),
        [],
        public_base_url="http://localhost:8080",
        event_sent_at=None,
        snapshot=snapshot if with_snapshot else None,
    )
    return _jobs(effects.outbox_rows)


def test_every_delivery_payload_lists_filled_in_runbook_steps() -> None:
    jobs = _build(with_snapshot=True)
    assert len(jobs) == 2
    for job in jobs:
        steps = job.content.runbook_steps
        assert steps[0].startswith("1. ")
        assert any(WF in step for step in steps)


def test_no_snapshot_leaves_steps_empty() -> None:
    assert all(not job.content.runbook_steps for job in _build(with_snapshot=False))
