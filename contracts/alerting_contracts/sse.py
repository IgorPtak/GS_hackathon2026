"""Server-sent events on GET /api/v1/stream and the Redis pub/sub messages behind them.

Wire format: `event: <type>` and `data: <SseEvent JSON>`. Producers publish the same JSON to
pub/sub channel `alerts.team.<team_id>` (team-scoped) or `broadcast` (everyone).
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field

from .alerts import Alert, AuditEntry, Delivery
from .api import PhoneMessage, UnknownSchemaSample
from .common import ConfigId, ContractModel, Severity
from .proposals import FixProposal
from .runbooks import ActionRun, ApprovalRequest


class _SseBase(ContractModel):
    at: datetime


class AlertCreatedEvent(_SseBase):
    type: Literal["alert.created"] = "alert.created"
    alert: Alert


class AlertUpdatedEvent(_SseBase):
    """Count, status or group membership changed. Dedup increments are coalesced to <= 1/s per alert."""

    type: Literal["alert.updated"] = "alert.updated"
    alert: Alert


class NotificationEvent(_SseBase):
    """Delivery through the `ui` channel: a toast for the team."""

    type: Literal["notification"] = "notification"
    alert_id: str
    team: ConfigId
    title: str
    severity: Severity
    delivery_id: int


class DeliveryUpdatedEvent(_SseBase):
    type: Literal["delivery.updated"] = "delivery.updated"
    delivery: Delivery


class PhoneMessageEvent(_SseBase):
    """Published on `broadcast`: the phone simulator shows every recipient's phone, whatever team is picked."""

    type: Literal["phone.message"] = "phone.message"
    message: PhoneMessage


class ActionRunUpdatedEvent(_SseBase):
    type: Literal["action_run.updated"] = "action_run.updated"
    action_run: ActionRun


class ApprovalRequestedEvent(_SseBase):
    type: Literal["approval.requested"] = "approval.requested"
    approval_request: ApprovalRequest


class ApprovalDecidedEvent(_SseBase):
    type: Literal["approval.decided"] = "approval.decided"
    approval_request: ApprovalRequest


class FixProposalEvent(_SseBase):
    type: Literal["fix_proposal.updated"] = "fix_proposal.updated"
    fix_proposal: FixProposal


class UnknownSchemaDetectedEvent(_SseBase):
    type: Literal["unknown_schema.detected"] = "unknown_schema.detected"
    sample: UnknownSchemaSample


class AuditAppendedEvent(_SseBase):
    """Published by every writer of audit_entries so the alert's audit trail updates live."""

    type: Literal["audit.appended"] = "audit.appended"
    entry: AuditEntry


class ConfigChangedEvent(_SseBase):
    """Also the payload of pub/sub channel `config.changed` that makes workers reload."""

    type: Literal["config.changed"] = "config.changed"
    kind: str
    id: ConfigId
    version: int


SseEvent = Annotated[
    AlertCreatedEvent
    | AlertUpdatedEvent
    | NotificationEvent
    | DeliveryUpdatedEvent
    | PhoneMessageEvent
    | ActionRunUpdatedEvent
    | ApprovalRequestedEvent
    | ApprovalDecidedEvent
    | FixProposalEvent
    | UnknownSchemaDetectedEvent
    | AuditAppendedEvent
    | ConfigChangedEvent,
    Field(discriminator="type"),
]
