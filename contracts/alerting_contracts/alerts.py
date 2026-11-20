"""Alerts, deliveries, outbox entries, stream jobs and audit entries."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from .common import Actor, ConfigId, ContractModel, Severity
from .config import ChannelType


class AlertStatus(StrEnum):
    open = "open"
    acknowledged = "acknowledged"
    resolved = "resolved"


class ResolutionReason(StrEnum):
    manual = "manual"
    source_resolved = "source_resolved"
    silence = "silence"


class AlertField(ContractModel):
    path: str
    value: Any = None


class GroupMember(ContractModel):
    """One distinct event fingerprint inside a group summary alert (drill-down row)."""

    fingerprint: str
    title: str
    count: int
    last_seen: datetime


class Alert(ContractModel):
    """Table alerts. One alert per (rule_id, fingerprint) per dedup window, or per group window."""

    id: str = Field(description="UUID v7.")
    rule_id: ConfigId
    team: ConfigId
    schema_profile_id: ConfigId
    source_id: ConfigId
    fingerprint: str
    group_key: str | None = None
    is_group_summary: bool = False
    group_members: list[GroupMember] = Field(default_factory=list)
    severity: Severity
    title: str
    body: str = ""
    fields: list[AlertField] = Field(default_factory=list)
    color: str = "orange"
    count: int = Field(default=1, ge=1, description="Events folded in by dedup.")
    first_seen: datetime
    last_seen: datetime
    status: AlertStatus = AlertStatus.open
    runbook_id: ConfigId | None = None
    last_event: dict[str, Any] = Field(description="Raw payload of the most recent event.")
    acknowledged_by: Actor | None = None
    acknowledged_at: datetime | None = None
    resolved_by: Actor | None = None
    resolved_at: datetime | None = None
    resolution_reason: ResolutionReason | None = None
    updated_at: datetime = Field(description="Any change, incl. count flushes; monotonic per alert.")


class DeliveryStatus(StrEnum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    delivered = "delivered"
    dead_lettered = "dead_lettered"
    suppressed = "suppressed"


class DeliveryPurpose(StrEnum):
    alert = "alert"
    approval_request = "approval_request"
    group_summary = "group_summary"


class NotificationContent(ContractModel):
    """Rendered once by the producer of the outbox row; channels only format it."""

    title: str
    body: str = ""
    severity: Severity
    fields: list[AlertField] = Field(default_factory=list)
    alert_url: str
    runbook_steps: list[str] = Field(default_factory=list, description="Rendered step texts.")
    approval_code: str | None = None


class DeliveryJob(ContractModel):
    """Payload of outbox kind `delivery`; stream `deliveries`, field `job`."""

    delivery_id: int = Field(description="= outbox entry id; delivery idempotency key.")
    alert_id: str
    team: ConfigId
    recipient_id: ConfigId | None = Field(default=None, description="None for the team-wide ui channel.")
    channel_id: ConfigId
    channel_type: ChannelType = Field(description="Selects the channel plugin; no config lookup needed.")
    purpose: DeliveryPurpose
    content: NotificationContent
    attempt: int = Field(default=0, ge=0, description="Failed attempts so far; travels with retries.")
    not_before: datetime | None = Field(default=None, description="Earliest time of the next attempt.")
    approval_request_id: str | None = None
    event_sent_at: datetime | None = Field(default=None, description="For end-to-end latency.")
    is_fallback: bool = False


class RunbookJob(ContractModel):
    """Payload of outbox kind `runbook_job`; stream `runbook-jobs`, field `job`."""

    job_type: Literal["start_runbook", "execute_action_run"]
    alert_id: str
    runbook_id: ConfigId
    action_run_id: str | None = None


class OutboxKind(StrEnum):
    delivery = "delivery"
    runbook_job = "runbook_job"


class OutboxEntry(ContractModel):
    """Table outbox. Written in the same transaction as the alert change that caused it."""

    id: int
    kind: OutboxKind
    alert_id: str
    payload: dict[str, Any] = Field(description="DeliveryJob or RunbookJob as JSON.")
    created_at: datetime
    relayed_at: datetime | None = None


class Delivery(ContractModel):
    """Table deliveries; one row per outbox delivery entry, updated by delivery workers."""

    id: int
    alert_id: str
    team: ConfigId
    recipient_id: ConfigId | None = None
    channel_id: ConfigId
    channel_type: ChannelType
    purpose: DeliveryPurpose
    status: DeliveryStatus
    attempt: int = 0
    last_error: str | None = None
    is_fallback: bool = False
    created_at: datetime
    updated_at: datetime
    delivered_at: datetime | None = None


class AuditVerb(StrEnum):
    alert_created = "alert_created"
    alert_grouped = "alert_grouped"
    alert_acknowledged = "alert_acknowledged"
    alert_resolved = "alert_resolved"
    delivery_delivered = "delivery_delivered"
    delivery_failed = "delivery_failed"
    delivery_dead_lettered = "delivery_dead_lettered"
    delivery_fallback = "delivery_fallback"
    delivery_suppressed = "delivery_suppressed"
    runbook_started = "runbook_started"
    action_run_started = "action_run_started"
    action_run_succeeded = "action_run_succeeded"
    action_run_failed = "action_run_failed"
    action_run_skipped = "action_run_skipped"
    approval_requested = "approval_requested"
    approval_decided = "approval_decided"
    fix_proposed = "fix_proposed"
    fix_decided = "fix_decided"


class AuditEntry(ContractModel):
    """Table audit_entries. Append-only."""

    id: int
    alert_id: str
    at: datetime
    actor: Actor
    verb: AuditVerb
    outcome: Literal["ok", "error", "pending"] = "ok"
    detail: dict[str, Any] = Field(default_factory=dict)
