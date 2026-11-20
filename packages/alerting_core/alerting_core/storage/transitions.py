"""Alert state transitions: open -> acknowledged -> resolved (or open -> resolved)."""

import asyncpg
from alerting_contracts.alerts import Alert, AlertStatus, AuditEntry, AuditVerb, ResolutionReason
from alerting_contracts.common import Actor

from .audit import append_audit
from .rows import ALERT_SELECT, alert_from_row


class AlertNotFoundError(LookupError):
    """No alert with that id (API: 404)."""


class InvalidTransitionError(ValueError):
    """The alert's current status does not allow the transition (API: 409 invalid_transition)."""


async def _lock_alert(connection: asyncpg.Connection, alert_id: str) -> Alert:
    record = await connection.fetchrow(
        f"SELECT {ALERT_SELECT} FROM alerts WHERE id = $1::uuid FOR UPDATE", alert_id
    )
    if record is None:
        raise AlertNotFoundError(alert_id)
    return alert_from_row(record)


async def acknowledge_alert(
    connection: asyncpg.Connection, alert_id: str, actor: Actor
) -> tuple[Alert, AuditEntry]:
    """Acknowledge an open alert; the caller publishes events after commit (publish_alert_change)."""
    async with connection.transaction():
        current = await _lock_alert(connection, alert_id)  # row lock: concurrent requests serialize
        if current.status is not AlertStatus.open:
            raise InvalidTransitionError(
                f"cannot acknowledge an alert that is {current.status.value}"
            )
        record = await connection.fetchrow(
            "UPDATE alerts SET status = 'acknowledged', acknowledged_by = $2, "
            "acknowledged_at = now(), "
            f"updated_at = now() WHERE id = $1::uuid RETURNING {ALERT_SELECT}",
            alert_id,
            actor.model_dump(mode="json"),
        )
        if record is None:
            raise AlertNotFoundError(alert_id)
        audit = await append_audit(connection, alert_id, actor, AuditVerb.alert_acknowledged)
    return alert_from_row(record), audit


async def resolve_alert(
    connection: asyncpg.Connection,
    alert_id: str,
    actor: Actor,
    reason: ResolutionReason = ResolutionReason.manual,
    comment: str | None = None,
) -> tuple[Alert, AuditEntry]:
    """Resolve an open or acknowledged alert; sets resolved_by/at and the resolution reason."""
    async with connection.transaction():
        current = await _lock_alert(connection, alert_id)
        if current.status is AlertStatus.resolved:
            raise InvalidTransitionError("cannot resolve an alert that is resolved")
        record = await connection.fetchrow(
            "UPDATE alerts SET status = 'resolved', resolved_by = $2, resolved_at = now(), "
            "resolution_reason = $3, updated_at = now() "
            f"WHERE id = $1::uuid RETURNING {ALERT_SELECT}",
            alert_id,
            actor.model_dump(mode="json"),
            reason.value,
        )
        if record is None:
            raise AlertNotFoundError(alert_id)
        detail: dict[str, str] = {"reason": reason.value}
        if comment:
            detail["comment"] = comment
        audit = await append_audit(
            connection, alert_id, actor, AuditVerb.alert_resolved, detail=detail
        )
    return alert_from_row(record), audit
