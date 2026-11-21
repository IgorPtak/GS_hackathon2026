"""Outbox rows for a newly created alert: one delivery per routed target, plus its runbook job."""

from dataclasses import dataclass, field
from datetime import datetime

from alerting_contracts.alerts import (
    Alert,
    AuditVerb,
    DeliveryJob,
    DeliveryPurpose,
    NotificationContent,
    OutboxKind,
    RunbookJob,
)
from alerting_contracts.common import Actor
from alerting_contracts.config import Rule
from alerting_core.config.registry import ConfigSnapshot
from alerting_core.logging import get_logger
from alerting_core.outbox import OutboxRow
from alerting_core.routing import DeliveryTarget, check_throttle, resolve_deliveries
from alerting_core.runbooks.rendering import render_runbook, runbook_step_texts
from alerting_core.storage.alerts_write import AuditRow
from redis.asyncio import Redis

log = get_logger(__name__)

PROCESSOR_ACTOR = Actor(id="system:processor")


@dataclass(slots=True)
class AlertSideEffects:
    outbox_rows: list[OutboxRow] = field(default_factory=list)
    audit_rows: list[AuditRow] = field(default_factory=list)


async def throttle_targets(
    redis: Redis,
    snapshot: ConfigSnapshot,
    rule: Rule,
    alert: Alert,
    source: str | None,
    now: datetime,
) -> tuple[list[DeliveryTarget], list[DeliveryTarget]]:
    """Route the alert and split its targets into (allowed, suppressed) by the rule's throttle.

    Runs before the batch transaction so no row lock is held across Redis round trips. If the
    insert later loses to a concurrent replica, its throttle counters were bumped for nothing;
    that only makes a throttle slightly stricter, never loses an alert.
    """
    targets = resolve_deliveries(
        rule,
        alert,
        teams=snapshot.of_kind("team"),
        recipients=snapshot.of_kind("recipient"),
        channels=snapshot.of_kind("channel"),
        now=now,
        source=source,
    )
    return await check_throttle(redis, rule, targets, now, alert_id=alert.id)


def _runbook_steps(rule: Rule, alert: Alert, snapshot: ConfigSnapshot | None) -> list[str]:
    """Numbered, filled-in runbook steps (empty without a runbook or snapshot)."""
    if snapshot is None or not rule.runbook:
        return []
    runbook = snapshot.of_kind("runbook").get(rule.runbook)
    if runbook is None:
        return []
    try:
        return runbook_step_texts(render_runbook(runbook, alert, snapshot.of_kind("action")))
    except (ValueError, TypeError, KeyError) as error:
        # Runs inside the persist transaction: a bad runbook must not fail and re-poison the batch.
        log.error(
            "runbook_render_failed",
            extra={"alert_id": alert.id, "rule_id": rule.id, "error": str(error)},
        )
        return []


def build_side_effects(
    rule: Rule,
    alert: Alert,
    allowed: list[DeliveryTarget],
    suppressed: list[DeliveryTarget],
    *,
    public_base_url: str,
    event_sent_at: datetime | None,
    purpose: DeliveryPurpose = DeliveryPurpose.alert,
    snapshot: ConfigSnapshot | None = None,
) -> AlertSideEffects:
    """Audit the creation, one delivery per allowed target, the runbook job (pure).

    A group summary is audited as `alert_grouped` and delivered with purpose `group_summary`.
    """
    effects = AlertSideEffects()
    verb = AuditVerb.alert_created
    detail: dict[str, object] = {"rule_id": rule.id}
    if alert.is_group_summary:
        verb = AuditVerb.alert_grouped
        detail |= {"group_key": alert.group_key, "members": len(alert.group_members)}
    effects.audit_rows.append(AuditRow(alert.id, PROCESSOR_ACTOR, verb, detail))
    content = NotificationContent(
        title=alert.title,
        body=alert.body,
        severity=alert.severity,
        fields=alert.fields,
        alert_url=f"{public_base_url.rstrip('/')}/alerts/{alert.id}",
        runbook_steps=_runbook_steps(rule, alert, snapshot),
    )
    for target in allowed:
        job = DeliveryJob(
            delivery_id=0,  # stamped with the outbox id by the relay
            alert_id=alert.id,
            team=alert.team,
            recipient_id=target.recipient_id,
            channel_id=target.channel_id,
            channel_type=target.channel_type,
            purpose=purpose,
            content=content,
            event_sent_at=event_sent_at,
        )
        effects.outbox_rows.append((OutboxKind.delivery, alert.id, job.model_dump(mode="json")))
    for target in suppressed:
        detail = {"recipient_id": target.recipient_id, "channel_id": target.channel_id}
        effects.audit_rows.append(
            AuditRow(alert.id, PROCESSOR_ACTOR, AuditVerb.delivery_suppressed, detail)
        )
    if rule.runbook:
        job = RunbookJob(job_type="start_runbook", alert_id=alert.id, runbook_id=rule.runbook)
        effects.outbox_rows.append((OutboxKind.runbook_job, alert.id, job.model_dump(mode="json")))
    return effects
