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
from alerting_core.outbox import OutboxRow
from alerting_core.routing import check_throttle, resolve_deliveries
from alerting_core.storage.alerts_write import AuditRow
from redis.asyncio import Redis

PROCESSOR_ACTOR = Actor(id="system:processor")


@dataclass(slots=True)
class AlertSideEffects:
    outbox_rows: list[OutboxRow] = field(default_factory=list)
    audit_rows: list[AuditRow] = field(default_factory=list)


async def plan_alert_side_effects(
    redis: Redis,
    snapshot: ConfigSnapshot,
    rule: Rule,
    alert: Alert,
    *,
    source: str | None,
    public_base_url: str,
    event_sent_at: datetime | None,
    now: datetime,
) -> AlertSideEffects:
    """Audit `alert_created`, route and throttle deliveries, and queue the rule's runbook."""
    effects = AlertSideEffects()
    effects.audit_rows.append(
        AuditRow(alert.id, PROCESSOR_ACTOR, AuditVerb.alert_created, {"rule_id": rule.id})
    )
    targets = resolve_deliveries(
        rule,
        alert,
        teams=snapshot.of_kind("team"),
        recipients=snapshot.of_kind("recipient"),
        channels=snapshot.of_kind("channel"),
        now=now,
        source=source,
    )
    allowed, suppressed = await check_throttle(redis, rule, targets, now, alert_id=alert.id)
    content = NotificationContent(
        title=alert.title,
        body=alert.body,
        severity=alert.severity,
        fields=alert.fields,
        alert_url=f"{public_base_url.rstrip('/')}/alerts/{alert.id}",
    )
    for target in allowed:
        job = DeliveryJob(
            delivery_id=0,  # stamped with the outbox id by the relay
            alert_id=alert.id,
            team=alert.team,
            recipient_id=target.recipient_id,
            channel_id=target.channel_id,
            channel_type=target.channel_type,
            purpose=DeliveryPurpose.alert,
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
